"""LightNav navigation with held forward motion and short turning pulses."""

import logging
import math
import os
import pickle
import socket
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import zmq


@dataclass(frozen=True)
class Settings:
    speed: float = 5.0  # Native Dogzilla units, not m/s.
    camera_timeout: float = 1.0
    prediction_timeout: float = 15.0
    goal_timeout: float = 1200.0

    def __post_init__(self):
        if any(not math.isfinite(v) or v < 0 for v in vars(self).values()):
            raise ValueError("Settings must be finite and nonnegative")
        if not 0 < self.speed <= 18:
            raise ValueError("Speed must be in (0, 18]")
        if min(self.camera_timeout, self.prediction_timeout, self.goal_timeout) <= 0:
            raise ValueError("Timeouts must be positive")

    @classmethod
    def from_env(cls):
        return cls(
            **{
                name: float(os.getenv(f"VLA_{name.upper()}", default))
                for name, default in vars(cls()).items()
            }
        )


@dataclass(frozen=True)
class Steering:
    cone_degrees: float = 25
    forward_duration: float = 0.10
    turn_duration: float = 0.35
    invert_yaw: bool = False
    settle_duration: float = 0.6

    def __post_init__(self):
        if type(self.invert_yaw) is not bool:
            raise ValueError("Invert yaw must be on or off")
        if type(self.settle_duration) not in (int, float) or not 0 <= self.settle_duration <= 3:
            raise ValueError("Use a post-turn settle delay between 0 and 3000 ms")
        ranges = (
            (self.cone_degrees, 5, 60),
            (self.forward_duration, 0.05, 0.5),
            (self.turn_duration, 0.05, 10),
        )
        if any(
            type(value) not in (int, float) or not low <= value <= high
            for value, low, high in ranges
        ):
            raise ValueError("Use a 5–60° cone, 50–500 ms forward and 50–10000 ms turn pulse")
        if self.forward_duration >= self.turn_duration:
            raise ValueError("Turn pulse must be longer than the forward correction")


def steering_decision(value, speed, steering):
    points = np.asarray(value, dtype=float)
    if (
        points.ndim != 2
        or points.shape[1] != 3
        or not 1 <= len(points) <= 16
        or not np.isfinite(points).all()
        or np.abs(points).max() > 4
    ):
        raise ValueError("Invalid LightNav waypoints")
    if np.abs(points).max() < 0.005:
        return None
    bearings = np.arctan2(points[:, 1], points[:, 0])
    useful = np.flatnonzero(np.hypot(points[:, 0], points[:, 1]) >= 0.08)
    outside = useful[np.abs(bearings[useful]) > math.radians(steering.cone_degrees)]
    final_yaw = math.atan2(math.sin(points[-1, 2]), math.cos(points[-1, 2]))
    if len(outside):
        index = int(outside[-1])
        heading = float(bearings[index])
        turning = True
    elif not len(useful) and abs(final_yaw) >= 0.15:
        index = len(points) - 1
        heading = final_yaw
        turning = True
    else:
        index = int(useful[min(1, len(useful) - 1)]) if len(useful) else len(points) - 1
        heading = float(bearings[index]) if len(useful) else 0.0
        turning = False

    forward = points[index, 0]
    vx = 0.0 if turning or forward < 0.03 else float(np.clip(8 * forward, 0, speed))
    requested = float(np.clip(60 * heading, -40, 40))
    if not turning and abs(heading) < 0.15:
        requested = 0.0
    turn = math.copysign(40 if turning else 30, requested) if requested else 0.0
    if steering.invert_yaw:
        turn = -turn
    duration = (steering.turn_duration if turning else steering.forward_duration) if turn else None
    return {
        "path": points.tolist(),
        "waypoint": index + 1,
        "heading_rad": heading,
        "maneuver": "turn" if turning else "forward",
        "requested_turn": requested,
        "command": (vx, 0.0, turn),
        "duration": duration,
    }


class BoundedHistoryAgent:
    """Limit SlowFast's full-episode buffer through the public observation API."""

    def __init__(self, agent, max_frames=16):
        if not isinstance(max_frames, int) or not 2 <= max_frames <= 64:
            raise ValueError("VLA_HISTORY_FRAMES must be an integer in [2, 64]")
        self.agent = agent
        self.max_frames = max_frames
        self.frames = deque(maxlen=max_frames)
        self.instruction = ""
        self._pending = self._fed = 0

    def reset(self, instruction=""):
        self.frames.clear()
        self.instruction = instruction
        self._pending = self._fed = 0
        self.agent.reset(instruction)

    def observe(self, image):
        self.frames.append(image.copy())
        self._pending += 1

    def predict_waypoints(self, instruction, *, task_type="tracking"):
        if self._fed + self._pending > self.max_frames:
            # SlowFast indexes from episode frame zero. Reset its frame IDs and
            # caches together before replaying the window; never reload weights.
            self.agent.reset(self.instruction)
            frames = list(self.frames)
            self._fed = 0
        else:
            frames = list(self.frames)[-self._pending :] if self._pending else []
        for image in frames:
            self.agent.observe(image)
            self._fed += 1
        self._pending = 0
        logging.info("LightNav history: %d/%d frames", self._fed, self.max_frames)
        return self.agent.predict_waypoints(instruction, task_type=task_type)


def load_agent(path):
    history_frames = int(os.getenv("VLA_HISTORY_FRAMES", "16"))
    if not 2 <= history_frames <= 64:
        raise ValueError("VLA_HISTORY_FRAMES must be an integer in [2, 64]")
    import torch
    from lightnav.tracking import build_tracking_agent

    if not Path(path).is_dir():
        raise RuntimeError(f"Checkpoint directory missing: {path}; see docs/vla.md")
    if not torch.cuda.is_available() or torch.version.hip:
        raise RuntimeError("LightNav requires the lab NVIDIA GPU; CUDA is unavailable")
    major, minor = torch.cuda.get_device_capability()
    if f"sm_{major}{minor}" not in torch.cuda.get_arch_list():
        raise RuntimeError("Torch does not include this GPU; use the pinned CUDA 12.6 wheels")
    os.environ.setdefault("LIGHTNAV_DTYPE", "float16")
    os.environ.setdefault("LIGHTNAV_ATTN", "sdpa")
    logging.info(
        "Loading LightNav on %s, Torch %s, CUDA %s",
        torch.cuda.get_device_name(),
        torch.__version__,
        torch.version.cuda,
    )
    agent = build_tracking_agent(
        path, backend="hf", device="cuda", task_key="vlnce", max_new_tokens=32
    )
    if agent.engine.bundle.model.dtype != torch.float16:
        raise RuntimeError("Expected FP16 model; build with patches/lightnav-fp16.patch")
    return BoundedHistoryAgent(agent, history_frames)


class Camera:
    def __init__(self, address="ipc:///tmp/video_frames_c.ipc", width=640, height=480):
        self.address, self.width, self.height = address, width, height
        self.context = self.socket = None

    def read(self):
        # Create/use/close the socket in its owning camera thread.
        if self.socket is None:
            self.context = zmq.Context()
            self.socket = self.context.socket(zmq.SUB)
            self.socket.setsockopt(zmq.SUBSCRIBE, b"")
            self.socket.setsockopt(zmq.CONFLATE, 1)
            self.socket.setsockopt(zmq.LINGER, 0)
            self.socket.setsockopt(zmq.MAXMSGSIZE, max(4096, self.width * self.height * 3))
            self.socket.connect(self.address)
        if not self.socket.poll(50):
            return None
        data = self.socket.recv()
        if len(data) != self.width * self.height * 3:
            raise ValueError("Camera frame does not match RGB dimensions")
        rgb = np.frombuffer(data, dtype=np.uint8).reshape(self.height, self.width, 3).copy()
        return time.monotonic(), rgb

    def close(self):
        if self.socket is not None:
            self.socket.close()
            self.context.term()


class Dog:
    def __init__(self, move=False, socket_factory=None):
        self.move = move
        self.socket = None
        self.socket_factory = socket_factory

    def send(self, name, args=None):
        if not self.move:
            return
        if self.socket is None:
            if self.socket_factory:
                self.socket = self.socket_factory()
            else:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.connect(("127.0.0.1", 5002))
            self.socket.settimeout(0.1)
        command = {"name": name}
        if args is not None:
            command["args"] = args
        self.socket.send(pickle.dumps(command))

    def velocity(self, command):
        logging.info("Dogi vx/vy/turn: %s%s", command, "" if self.move else " (dry run)")
        for method, value in zip(("move_x", "move_y", "turn"), command, strict=True):
            self.send(method, (value,))

    def stop(self):
        self.send("stop")

    def clear_yaw(self):
        self.send("turn", (0,))

    def close(self):
        if self.socket is not None:
            self.socket.close()


class Navigation:
    def __init__(self, camera, dog, agent_factory, settings=None):
        self.camera, self.dog, self.agent_factory = camera, dog, agent_factory
        self.settings = settings or Settings()
        self.changed = threading.Condition()
        self.closed = threading.Event()
        self.ready = self.failed = False
        self.generation = 0
        self.state = "loading"
        self.goal = self.error = self.started_at = self.predicting_at = None
        self.frames = deque(maxlen=64)
        self.latest = None
        self.command = (0, 0, 0)
        self.turn_until = None
        self.manual_until = None
        self.steering = Steering()
        self.decision = None
        self.camera_pitch = None
        self.predictions = self.discarded = 0
        self.latency_ms = None
        self.threads = []

    def start(self):
        if self.threads or self.closed.is_set():
            raise RuntimeError("Navigation can only start once")
        self.dog.stop()
        self.threads = [
            threading.Thread(target=fn, daemon=True)
            for fn in (self._camera_loop, self._inference_loop)
        ]
        for thread in self.threads:
            thread.start()

    def _send_stop(self):
        self.command = (0, 0, 0)
        self.turn_until = None
        self.manual_until = None
        try:
            self.dog.stop()
        except Exception as exc:
            self.failed = True
            self.state, self.error = "error", f"Stop send failed: {exc}"
            raise

    def stop(self, error=None, state="stopped"):
        with self.changed:
            self.generation += 1
            self.goal = self.predicting_at = None
            self.frames.clear()
            self.state, self.error = ("error" if error else state), error
            if error:
                logging.error("%s", error)
            try:
                self._send_stop()
            finally:
                self.changed.notify_all()

    def set_goal(self, text):
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 240:
            raise ValueError("Use an instruction of 1-240 characters")
        with self.changed:
            if not self.ready or self.closed.is_set() or self.failed:
                raise RuntimeError("Navigation is not ready; check the worker status")
            self.stop()
            self.goal, self.state = text.strip(), "navigating"
            self.started_at = time.monotonic()
            self.predictions, self.latency_ms = 0, None
            self.decision = None
            self.changed.notify_all()

    def reset(self):
        with self.changed:
            self.stop()
            self.predictions = self.discarded = 0
            self.latency_ms = None
            self.decision = None

    def configure_steering(self, data):
        required = {"cone_degrees", "forward_duration", "turn_duration"}
        allowed = required | {"invert_yaw", "settle_duration"}
        if not isinstance(data, dict) or not required <= data.keys() <= allowed:
            raise ValueError("Send cone angle and both pulse durations")
        steering = Steering(**data)
        with self.changed:
            if self.closed.is_set() or self.failed:
                raise RuntimeError("Navigation is unavailable")
            self.stop()
            self.steering = steering
            self.decision = None

    def set_camera_pitch(self, pitch):
        if type(pitch) is not int or not -20 <= pitch <= 20:
            raise ValueError("Camera pitch must be a whole number from -20 to 20")
        with self.changed:
            if self.closed.is_set():
                raise RuntimeError("Navigation is unavailable")
            self.stop()
            self.dog.send("attitude", ("p", pitch))
            self.camera_pitch = pitch
            self.decision = None

    def manual_move(self, data):
        limits = {"vx": 20, "vy": 18, "yaw": 70, "duration": 1}
        if (
            not isinstance(data, dict)
            or data.keys() != limits.keys()
            or any(
                type(data[key]) not in (int, float) or not -limit <= data[key] <= limit
                for key, limit in limits.items()
            )
            or data["duration"] < 0.1
        ):
            raise ValueError("Use vx ±20, vy ±18, yaw ±70 and a duration of 0.1–1 s")
        with self.changed:
            if not self.ready or self.closed.is_set() or self.failed:
                raise RuntimeError("Navigation is unavailable")
            self.stop()
            command = (data["vx"], data["vy"], data["yaw"])
            if any(command):
                try:
                    self.dog.velocity(command)
                except Exception:
                    self.stop("Manual command send failed")
                    raise
                self.command, self.state = command, "manual"
                self.manual_until = time.monotonic() + data["duration"]
            self.decision = None

    def status(self):
        with self.changed:
            age = None if self.latest is None else time.monotonic() - self.latest[0]
            return {
                "state": self.state,
                "generation": self.generation,
                "ready": self.ready and not self.failed and not self.closed.is_set(),
                "goal": self.goal,
                "command": self.command,
                "error": self.error,
                "predictions": self.predictions,
                "discarded_results": self.discarded,
                "latency_ms": self.latency_ms,
                "camera_ok": age is not None and age <= self.settings.camera_timeout,
                "move": self.dog.move,
                "steering": asdict(self.steering),
                "decision": self.decision,
                "camera_pitch": self.camera_pitch,
            }

    def _current(self, generation):
        return not self.closed.is_set() and self.goal and generation == self.generation

    def _camera_loop(self):
        sampled = float("-inf")
        try:
            while not self.closed.is_set():
                frame = self.camera.read()
                with self.changed:
                    now = time.monotonic()
                    if self.manual_until is not None and now >= self.manual_until:
                        self.stop()
                    if frame is not None:
                        self.latest = frame
                        if self.goal and frame[0] - sampled >= 0.25:
                            self.frames.append(frame)
                            sampled = frame[0]
                        self.changed.notify_all()
                    if self.goal:
                        last = self.latest[0] if self.latest else self.started_at
                        if now - last > self.settings.camera_timeout:
                            self.stop("Camera timed out")
                        elif now - self.started_at > self.settings.goal_timeout:
                            self.stop("Goal timed out")
                        elif (
                            self.predicting_at is not None
                            and now - self.predicting_at > self.settings.prediction_timeout
                        ):
                            self.stop("Prediction timed out")
                        if self.goal and self.turn_until is not None and now >= self.turn_until:
                            # End yaw independently of GPU inference; keep forward motion.
                            self.command = (self.command[0], 0.0, 0.0)
                            self.dog.clear_yaw()
                            self.turn_until = None
                            self.changed.notify_all()
        except Exception as exc:
            with self.changed:
                self.failed = True
                self.stop(f"Camera failed: {exc}")
        finally:
            self.camera.close()

    def _inference_loop(self):
        try:
            agent = self.agent_factory()
        except Exception as exc:
            with self.changed:
                if not self.closed.is_set():
                    self.failed = True
                    self.stop(f"Model load failed: {exc}")
            return
        with self.changed:
            if self.closed.is_set() or self.failed:
                return
            self.ready, self.state = True, "ready"
            self.changed.notify_all()
        previous, observed = None, float("-inf")
        while not self.closed.is_set():
            observation = self._wait_for_frames(observed)
            if observation is None:
                continue
            generation, goal, capture, frames = observation
            try:
                if generation != previous:
                    agent.reset(goal)
                    previous = generation
                for _, image in frames:
                    agent.observe(image)
                observed = capture[0]
                points, _, latency_ms = agent.predict_waypoints(goal, task_type="vlnce_traj")
                self._apply_prediction(generation, capture[0], points, latency_ms)
            except Exception as exc:
                with self.changed:
                    if self._current(generation):
                        self.stop(f"Navigation failed: {exc}")

    def _wait_for_frames(self, observed):
        with self.changed:
            self.changed.wait_for(lambda: self.closed.is_set() or self.goal)
            if self.closed.is_set():
                return None
            generation, goal = self.generation, self.goal
            after_turn = self.decision and self.decision["maneuver"] == "turn"
            if after_turn:
                self.changed.wait_for(
                    lambda: not self._current(generation) or self.turn_until is None
                )
            after = time.monotonic()
            if after_turn:
                # Allow the queued yaw stop and camera stream to catch up.
                after += self.steering.settle_duration
            self.changed.wait_for(
                lambda: (
                    not self._current(generation)
                    or (self.latest is not None and self.latest[0] >= after)
                )
            )
            if not self._current(generation):
                return None
            capture = self.latest
            frames = [frame for frame in self.frames if frame[0] > observed]
            if not frames or frames[-1][0] < capture[0]:
                frames.append(capture)
            self.predicting_at = capture[0]
            return generation, goal, capture, frames

    def _apply_prediction(self, generation, captured_at, points, latency_ms):
        with self.changed:
            if not self._current(generation):
                self.discarded += 1
                return
            now = time.monotonic()
            if now - captured_at > self.settings.prediction_timeout:
                raise TimeoutError("Prediction expired")
            if now - self.latest[0] > self.settings.camera_timeout:
                raise TimeoutError("Camera timed out")
            self.predicting_at = None
            self.predictions += 1
            self.latency_ms = float(latency_ms)
            decision = steering_decision(points, self.settings.speed, self.steering)
            if decision is None:
                self.decision = None
                self.stop(state="completed")
                return
            self.decision = {**decision, "age_ms": (now - captured_at) * 1000}
            self.command = decision["command"]
            self.dog.velocity(self.command)
            duration = decision["duration"]
            self.turn_until = time.monotonic() + duration if duration else None

    def close(self):
        with self.changed:
            if self.closed.is_set():
                return
            self.closed.set()
        try:
            self.stop()
        finally:
            for thread in self.threads:
                thread.join(timeout=0.5)
            self.dog.close()
