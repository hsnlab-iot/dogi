"""VLA browser relay. The model runs in the separate vla.py worker."""

import logging
import threading

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO
from werkzeug.middleware.proxy_fix import ProxyFix

from vla_runtime import Dog

PORT = 5061
app = Flask(__name__, static_folder="./static")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
# Native threads keep worker acknowledgements independent of browser handlers.
socketio = SocketIO(
    app, async_mode="threading", cors_allowed_origins="*", ping_interval=2, ping_timeout=5
)
state_lock = threading.RLock()
command_lock = threading.Lock()
worker_sid = owner_sid = None
fallback_dog = Dog()  # Reuse one local socket for fallback Stops.
status = {"state": "offline", "ready": False, "command": [0, 0, 0]}


def publish_status(data):
    global status
    with state_lock:
        status = dict(data)
        socketio.emit("vla_status", status)


def fallback_stop():
    # The proxy accepts Stop from another local sender even during its owner lease.
    fallback_dog.stop()


def call_worker(event, data=None, manual_sid=None):
    """Commands are serialized, and handlers in vla.py never wait for inference."""
    global owner_sid
    with command_lock:
        with state_lock:
            sid = worker_sid
            if manual_sid is not None:
                busy = status.get("goal") or status.get("state") == "manual"
                if manual_sid == sid or (busy and manual_sid != owner_sid):
                    return {"ok": False, "error": "Use the browser controlling the robot"}
                if not socketio.server.manager.is_connected(manual_sid, "/"):
                    return {"ok": False, "error": "Browser disconnected"}
                owner_sid = manual_sid
        if sid is None:
            return {"ok": False, "error": "VLA worker is offline; select the VLA tab"}
        try:
            result = socketio.call(event, data, to=sid, timeout=2)
            if not isinstance(result, dict) or result.get("ok") is not True:
                return (
                    result
                    if isinstance(result, dict)
                    else {"ok": False, "error": "Invalid worker reply"}
                )
            with state_lock:
                if sid == worker_sid and isinstance(result.get("status"), dict):
                    publish_status(result["status"])
            return result
        except Exception:
            logging.exception("VLA worker did not acknowledge %s", event)
            try:
                fallback_stop()
            except Exception:
                logging.exception("VLA fallback Stop failed")
            socketio.server.disconnect(sid)
            return {"ok": False, "error": "VLA worker disconnected or timed out; select VLA again"}


@app.route("/")
def index():
    return render_template("web_vla.html")


@app.post("/shutdown")
def shutdown_worker():
    # Called by web_main in the same container before destroying the tmux session.
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify(ok=False, error="Local endpoint"), 403
    with state_lock:
        if worker_sid is None:
            return jsonify(ok=True)
    result = call_worker("client_shutdown")
    return jsonify(result), 200 if result.get("ok") else 503


@socketio.on("connect")
def handle_connect(auth=None):
    global worker_sid, status
    if isinstance(auth, dict) and auth.get("role") == "worker":
        if request.remote_addr not in ("127.0.0.1", "::1"):
            return False
        with state_lock:
            if worker_sid is not None:
                return False
            worker_sid = request.sid
            status = {
                "state": "loading",
                "ready": False,
                "command": [0, 0, 0],
                "generation": -1,
            }
            socketio.emit("vla_status", status)
    else:
        with state_lock:
            socketio.emit("vla_status", status, to=request.sid)


@socketio.on("disconnect")
def handle_disconnect(reason=None):
    global worker_sid, owner_sid
    with state_lock:
        worker_left = request.sid == worker_sid
        owner_left = request.sid == owner_sid
        if worker_left:
            worker_sid = owner_sid = None
        elif owner_left:
            owner_sid = None
    if worker_left:
        try:
            fallback_stop()
        except Exception:
            logging.exception("VLA disconnect Stop failed")
        publish_status(
            {
                "state": "offline",
                "ready": False,
                "command": [0, 0, 0],
                "error": "Worker stopped; select VLA again",
            }
        )
    elif owner_left:
        call_worker("client_abort")


@socketio.on("prompt")
def handle_prompt(data=None):
    global owner_sid
    text = data.get("prompt") if isinstance(data, dict) else None
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 240:
        return {"ok": False, "error": "Use an instruction of 1-240 characters"}
    with state_lock:
        if request.sid == worker_sid:
            return {"ok": False, "error": "Use the browser to set a goal"}
        owner_sid = request.sid
    return call_worker("client_prompt", {"prompt": text.strip()})


@socketio.on("abort_prompt")
def handle_abort(data=None):
    return call_worker("client_abort")


@socketio.on("new")
def handle_new(data=None):
    return call_worker("client_new")


def adjust_worker(event, data):
    with state_lock:
        if request.sid == worker_sid or (status.get("goal") and request.sid != owner_sid):
            return {"ok": False, "error": "Use the browser controlling the current goal"}
    return call_worker(event, data)


@socketio.on("steering")
def handle_steering(data=None):
    return adjust_worker("client_steering", data)


@socketio.on("camera_pitch")
def handle_camera_pitch(data=None):
    return adjust_worker("client_camera_pitch", data)


@socketio.on("manual_move")
def handle_manual_move(data=None):
    return call_worker("client_manual_move", data, manual_sid=request.sid)


@socketio.on("ui_update")
def handle_ui_update(data=None):
    with state_lock:
        if request.sid != worker_sid or not isinstance(data, dict):
            return
        incoming = data.get("data")
        if data.get("type") != "status" or not isinstance(incoming, dict):
            return
        if incoming.get("generation", -1) < status.get("generation", -1):
            return
        publish_status(incoming)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=PORT, allow_unsafe_werkzeug=True)
