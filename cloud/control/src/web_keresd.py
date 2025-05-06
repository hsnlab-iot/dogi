from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import pickle
import socket
import time
import threading
from urllib.parse import urlparse
import socket

PORT = 5053

app = Flask(__name__)

socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*")

# Open UDP socket on port 5053 to receive action events
udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_socket.bind(('0.0.0.0', PORT))

def listen_for_actions():
    while True:
        data, addr = udp_socket.recvfrom(2048)
        action = pickle.loads(data)
        print('Received action:', action)

        if action.get('action') == 'xtext':
            print('Emitting xtext :', action.get('text'))
            socketio.emit('xtext', action.get('text'))
        elif action.get('action') == 'entext':
            print('Emitting entext :', action.get('text'))
            socketio.emit('entext', action.get('text'))
        elif action.get('action') == 'ball':
            socketio.emit('ball', action.get('found'))
        elif action.get('action') == 'obstacle':
            socketio.emit('obstacle', action.get('found'))
        else:
            print('Unknown action:', action.get('action'))

# Create and start the listener thread
listener_thread = threading.Thread(target=listen_for_actions)
listener_thread.start()

@app.route('/')
def index():
    host = urlparse(request.url_root).hostname
    return render_template('web_keresd.html', host=host)


@socketio.on_error()  # Handle socketio errors
def handle_error(e):
    print('SocketIO Error:', e)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=PORT)
