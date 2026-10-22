import os

from flask import Flask, render_template, request
from jinja2 import FileSystemLoader, ChoiceLoader
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_socketio import SocketIO, emit
from urllib.parse import urlparse

import config

PORT = 5061

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_STT_DIR = os.path.join(BASE_DIR, "static-stt")
DEFAULT_TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

config.init()

app = Flask(__name__, static_folder='./static')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

app.jinja_loader = ChoiceLoader([
    FileSystemLoader(DEFAULT_TEMPLATES_DIR),
    FileSystemLoader(STATIC_STT_DIR),
])

socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*", socketio_path='/socket.io/')

@app.route('/')
def index():
    host = urlparse(request.url_root).hostname
    return render_template('web_vla.html', host=host)

@socketio.on('connect')
def handle_connect():
    print('VLA client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('VLA client disconnected')


@socketio.on('prompt')
def handle_prompt(data):
    socketio.emit("client_prompt", data)


@socketio.on('abort_prompt')
def handle_abort():
    socketio.emit("client_abort")


@socketio.on('new')
def handle_new():
    socketio.emit("client_new")


# ui_update comes from vla.py
@socketio.on('ui_update')
def handle_ui_update(data):
    if not isinstance(data, dict) or 'type' not in data:
        return

    if data['type'] == 'prompt':
        socketio.emit('ui_update_prompt', data)


@socketio.on_error()
def handle_error(e):
    print('SocketIO Error:', e)


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=PORT)
