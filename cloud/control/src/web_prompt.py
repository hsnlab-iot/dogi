import os

from flask import Flask, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_socketio import SocketIO, emit
import pickle
import socket
import time
import threading
from urllib.parse import urlparse

import config
import utils
import base64
from io import BytesIO
from PIL import Image

PORT = 5056

config.init()

app = Flask(__name__, static_folder='./static')
#app.config['SECRET_KEY'] = 'secret_key'
# This tells Flask it is behind exactly 1 reverse proxy and 
# forces it to generate correct URLs automatically
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*", socketio_path='/socket.io/')

@app.route('/')
def index():
    host = urlparse(request.url_root).hostname
    return render_template('web_prompt.html', host=host)

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('prompt')
def handle_event(data):
    socketio.emit("client_prompt", data)
    pass

@socketio.on('new')
def handle_event():
    socketio.emit("client_new")
    pass

# ui_update is coming from prompt.py
@socketio.on('ui_update')
def handle_event(data):
    print(data)
    if data['type'] == 'tools':
        socketio.emit('ui_update_tools', data)
    elif data['type'] == 'response':
        socketio.emit('ui_update_response', data)
    elif data['type'] == 'stats':
        socketio.emit('ui_update_stats', data)
    elif data['type'] == 'tools_response':
        socketio.emit('ui_update_tools_response', data)
    elif data['type'] == 'tool_selection':
        socketio.emit('ui_update_tool_selection', data)
    elif data['type'] == 'prompt':
        socketio.emit('ui_update_prompt', data)

@socketio.on('reload')
def handle_event(data):
    pass

@socketio.on_error()  # Handle socketio errors
def handle_error(e):
    print('SocketIO Error:', e)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=PORT)
