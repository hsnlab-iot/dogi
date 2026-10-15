import os

from flask import Flask, render_template, request
from jinja2 import FileSystemLoader, ChoiceLoader
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_socketio import SocketIO, emit
import pickle
import socket
import time
import threading
from urllib.parse import urlparse
import subprocess

import config
import utils
import base64
from io import BytesIO
from PIL import Image
import qrcode
import re

PORT = 5058
ROOM_ID = os.getenv("ABLY_ROOM_ID", "dogy-chat")
ABLY_USER_KEY = os.getenv("ABLY_USER_KEY")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_STT_DIR = os.path.join(BASE_DIR, "static-stt")
DEFAULT_TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

config.init()

app = Flask(__name__, static_folder='./static')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Tell Jinja2 to search in both templates/ and static-stt/
app.jinja_loader = ChoiceLoader([
    FileSystemLoader(DEFAULT_TEMPLATES_DIR),
    FileSystemLoader(STATIC_STT_DIR),
])

socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*", socketio_path='/socket.io/')

# Global in-memory storage for the latest QR Data URI
latest_qr_data_uri = None


# --- QR CODE GENERATION HELPER ---
def generate_qr_base64(url):
    """Generates a PNG QR code in memory and converts it to a Base64 Data URI."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{img_str}"


# --- PINGGY TUNNEL & QR BACKGROUND WORKER ---
def pinggy_qr_worker():
    global latest_qr_data_uri

    path_param = f"user.html?room={ROOM_ID}"

    while True:
        print("[PINGGY-AGENT] Launching SSH tunnel for User QR...")
        cmd = [
            "ssh",
            "-T",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ServerAliveInterval=30",
            "-p", "443",
            f"-R0:localhost:{PORT}",
            f"{path_param}@a.pinggy.io"
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            os.set_blocking(proc.stdout.fileno(), False)
        except Exception as e:
            print(f"[PINGGY-AGENT] Error launching SSH process: {e}")
            time.sleep(10)
            continue

        extracted_url = None
        start_time = time.time()
        buffer = ""

        while time.time() - start_time < 15:
            try:
                chunk = proc.stdout.read()
                if chunk:
                    buffer += chunk
                    match = re.search(
                        r'https://[a-zA-Z0-9-]+\.(run\.pinggy-free\.link|free\.pinggy\.net|pinggy\.link)',
                        buffer
                    )
                    if match:
                        extracted_url = match.group(0) + f"/{path_param}"
                        print(f"[PINGGY-AGENT] Tunnel URL extracted successfully: {extracted_url}")
                        break
            except (IOError, TypeError):
                pass
            time.sleep(0.3)

        if extracted_url:
            latest_qr_data_uri = generate_qr_base64(extracted_url)
            socketio.emit('update_qr', {
                'qr_url': latest_qr_data_uri,
                'label': 'Scan to Connect'
            })
            print("[PINGGY-AGENT] QR code generated and broadcasted via Socket.IO")

            while proc.poll() is None:
                time.sleep(5)

            print("[PINGGY-AGENT] Tunnel connection closed. Reconnecting...")
        else:
            print("[PINGGY-AGENT] Timeout / Failed to extract URL from process output.")
            proc.kill()

        time.sleep(5)


@app.route('/')
def index():
    host = urlparse(request.url_root).hostname
    return render_template('web_agent.html', host=host)


@app.route('/user.html')
def user_page():
    return render_template('user.html', room_id=ROOM_ID, client_api_key=ABLY_USER_KEY)


@socketio.on('connect')
def handle_connect():
    print('Agent client connected')
    if latest_qr_data_uri:
        emit('update_qr', {
            'qr_url': latest_qr_data_uri,
            'label': 'Scan to Connect'
        })


@socketio.on('disconnect')
def handle_disconnect():
    print('Agent client disconnected')


@socketio.on('prompt')
def handle_prompt(data):
    socketio.emit("client_prompt", data)


@socketio.on('abort_prompt')
def handle_abort():
    socketio.emit("client_abort")


@socketio.on('new')
def handle_new():
    socketio.emit("client_new")


@socketio.on('speak')
def handle_speak(data):
    socketio.emit("client_speak", data)


# ui_update comes from agent.py
@socketio.on('ui_update')
def handle_ui_update(data):
    if not isinstance(data, dict) or 'type' not in data:
        return

    update_type = data['type']
    if update_type == 'tools':
        socketio.emit('ui_update_tools', data)
    elif update_type == 'response':
        socketio.emit('ui_update_response', data)
    elif update_type == 'stats':
        socketio.emit('ui_update_stats', data)
    elif update_type == 'tools_response':
        socketio.emit('ui_update_tools_response', data)
    elif update_type == 'tool_selection':
        socketio.emit('ui_update_tool_selection', data)
    elif update_type == 'prompt':
        socketio.emit('ui_update_prompt', data)
    elif update_type == 'prompt_insert':
        socketio.emit('ui_update_prompt_insert', data)


@socketio.on('reload')
def handle_reload(data):
    pass


@socketio.on('snapshot')
def handle_snapshot(data):
    print(f'Snapshot received: {data}')
    socketio.emit('ui_update_tools_response', data)


@socketio.on_error()
def handle_error(e):
    print('SocketIO Error:', e)


if __name__ == '__main__':
    qr_thread = threading.Thread(target=pinggy_qr_worker, daemon=True)
    qr_thread.start()

    socketio.run(app, host='0.0.0.0', port=PORT)

