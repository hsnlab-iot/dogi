"""Socket.IO worker for LightNav navigation and manual VLA controls."""

import logging
import os
import signal
import threading

import socketio

from vla_runtime import Camera, Dog, Navigation, Settings, load_agent

PORT = 5061
MODEL_PATH = os.getenv("LIGHTNAV_MODEL_PATH", "/models/LightNav-0")


def run_worker():
    navigation = Navigation(Camera(), Dog(), lambda: load_agent(MODEL_PATH), Settings.from_env())
    sio = socketio.Client(reconnection=False)
    shutdown = threading.Event()
    stopping = threading.Event()

    def interrupt(_signum, _frame):
        stopping.set()
        shutdown.set()

    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupt)

    def worker_status():
        status = navigation.status()
        status["ready"] = status["ready"] and not stopping.is_set()
        return status

    def perform(action, *args):
        if stopping.is_set() and action != navigation.stop:
            return {"ok": False, "error": "Worker is shutting down"}
        try:
            action(*args)
            return {"ok": True, "status": worker_status()}
        except Exception as exc:
            logging.exception("VLA command failed")
            return {"ok": False, "error": str(exc)}

    @sio.on("client_prompt")
    def handle_prompt(data=None):
        return perform(navigation.set_goal, data.get("prompt") if isinstance(data, dict) else None)

    @sio.on("client_abort")
    def handle_stop(data=None):
        return perform(navigation.stop)

    @sio.on("client_new")
    def handle_new(data=None):
        return perform(navigation.reset)

    @sio.on("client_steering")
    def handle_steering(data=None):
        return perform(navigation.configure_steering, data)

    @sio.on("client_camera_pitch")
    def handle_camera_pitch(data=None):
        return perform(navigation.set_camera_pitch, data)

    @sio.on("client_manual_move")
    def handle_manual_move(data=None):
        return perform(navigation.manual_move, data)

    @sio.on("client_shutdown")
    def handle_shutdown(data=None):
        stopping.set()
        # Stay connected until the ACK is delivered and web_main kills tmux.
        # Disconnecting here can race the Socket.IO acknowledgement packet.
        return perform(navigation.stop)

    @sio.event
    def disconnect(*_args):
        stopping.set()
        shutdown.set()
        if not navigation.closed.is_set():
            perform(navigation.stop)

    try:
        sio.connect(
            f"http://127.0.0.1:{PORT}",
            socketio_path="/socket.io/",
            auth={"role": "worker"},
            wait_timeout=10,
        )
        navigation.start()
        while not shutdown.is_set():
            sio.emit("ui_update", {"type": "status", "data": worker_status()})
            shutdown.wait(0.25)
    finally:
        stopping.set()
        shutdown.set()
        try:
            navigation.close()
        finally:
            if sio.connected:
                sio.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_worker()
