from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import pickle
import socket
import time
import threading
from urllib.parse import urlparse
import socket

app = Flask(__name__)

@app.route('/')
def index():
    host = urlparse(request.url_root).hostname
    return render_template('web_kovesd.html', host=host)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5054)
