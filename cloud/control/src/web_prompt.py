import os

from flask import Flask, render_template, request
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

app = Flask(__name__)
#app.config['SECRET_KEY'] = 'secret_key'
socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*")

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

@socketio.on('tools')
def handle_event(data):
    socketio.emit('ui_update_tools', data)

@socketio.on('reload')
def handle_event(data):
    pass

@socketio.on_error()  # Handle socketio errors
def handle_error(e):
    print('SocketIO Error:', e)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=PORT)
