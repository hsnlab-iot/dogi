from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import pickle
import socket
import time
import threading
from urllib.parse import urlparse
import socket

app = Flask(__name__)

socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*")

# Open UDP socket on port 5004 to receive action events
udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_socket.bind(('0.0.0.0', 5004))

def listen_for_actions():
    while True:
        data, addr = udp_socket.recvfrom(1024)
        action = pickle.loads(data)
        print('Received action:', action)

        if action.get('action'):
            socketio.emit('action', action.get('data'))

# Create and start the listener thread
listener_thread = threading.Thread(target=listen_for_actions)
listener_thread.start()

@app.route('/')
def index():
    host = urlparse(request.url_root).hostname
    return render_template('web_mutasd.html', host=host)


@socketio.on_error()  # Handle socketio errors
def handle_error(e):
    print('SocketIO Error:', e)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5054)
