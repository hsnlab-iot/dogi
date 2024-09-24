from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import pickle
import socket
import time
import threading
from urllib.parse import urlparse

inMotion = False
lock = threading.Lock()

app = Flask(__name__)
#app.config['SECRET_KEY'] = 'secret_key'
socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*")

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.connect(('localhost', 5002))

joy1_odata = None
joy2_attitude = [0, 0, 0]

@app.route('/')
def index():
    host = urlparse(request.url_root).hostname
    return render_template('joy.html', host=host)

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('joy1')
def handle_event(data):
    global joy1_odata
    #print('Received event:', data)
    if data == "E" and joy1_odata != "E":
        sock.send(pickle.dumps({'name': 'turn', 'args': (-10, )}))
    elif data == "W" and joy1_odata != "W":
        sock.send(pickle.dumps({'name': 'turn', 'args': (10, )}))
    elif data == "N" and joy1_odata != "N":
        sock.send(pickle.dumps({'name': 'forward', 'args': (10, )}))
    elif data == "S" and joy1_odata != "S":
        sock.send(pickle.dumps({'name': 'back', 'args': (10, )}))
    elif data == "C" and joy1_odata != "C":
        sock.send(pickle.dumps({'name': 'stop'}))
    joy1_odata = data

@socketio.on('joy2')
def handle_event(data):
    global joy2_attitude
    #print('Received event:', data)
    if data == "W":
        if joy2_attitude[2] < 16:
            joy2_attitude[2] += 1
        sock.send(pickle.dumps({'name': 'attitude', 'args': (['y'], [joy2_attitude[2]])}))
    if data == "E":
        if joy2_attitude[2] > -16:
            joy2_attitude[2] -= 1
        sock.send(pickle.dumps({'name': 'attitude', 'args': (['y'], [joy2_attitude[2]])}))
    if data == "N":
        if joy2_attitude[1] > -22:
            joy2_attitude[1] -= 1
        sock.send(pickle.dumps({'name': 'attitude', 'args': (['p'], [joy2_attitude[1]])}))
    if data == "S":
        if joy2_attitude[1] < 22:
            joy2_attitude[1] += 1
        sock.send(pickle.dumps({'name': 'attitude', 'args': (['p'], [joy2_attitude[1]])}))

@socketio.on('action')
def handle_event(data):
    global inMotion
    #print('Received event:', data)
    
    with lock:
        if inMotion:
            return
        inMotion = True

    if data == "reset":
        sock.send(pickle.dumps({'name': 'reset'}))
    if data == "pee":
        sock.send(pickle.dumps({'name': 'action', 'args': (11, )}))
    if data == "wave":
        sock.send(pickle.dumps({'name': 'action', 'args': (13, )}))
    if data == "look":
        sock.send(pickle.dumps({'name': 'attitude', 'args': (['r', 'p', 'y'], [0, 22, 0])}))
        time.sleep(1.5)
        sock.send(pickle.dumps({'name': 'attitude', 'args': (['r', 'p', 'y'], [0, 22, 16])}))
        time.sleep(1.5)
        sock.send(pickle.dumps({'name': 'attitude', 'args': (['r', 'p', 'y'], [0, 22, -16])}))
        time.sleep(1.5)
        sock.send(pickle.dumps({'name': 'attitude', 'args': (['r', 'p', 'y'], [0, 0, 0])}))
    if data == "sit":
        sock.send(pickle.dumps({'name': 'reset'}))
        time.sleep(1)
        sock.send(pickle.dumps({'name': 'motor', 'args': ([32, 93])}))
        sock.send(pickle.dumps({'name': 'motor', 'args': ([42, 93])}))
        sock.send(pickle.dumps({'name': 'motor', 'args': ([31, -73])}))
        sock.send(pickle.dumps({'name': 'motor', 'args': ([41, -73])}))
        sock.send(pickle.dumps({'name': 'motor', 'args': ([12, 10])}))
        sock.send(pickle.dumps({'name': 'motor', 'args': ([22, 10])}))
        sock.send(pickle.dumps({'name': 'motor', 'args': ([11, 30])}))
        sock.send(pickle.dumps({'name': 'motor', 'args': ([21, 30])}))
    
    with lock:
        inMotion = False

@socketio.on_error()  # Handle socketio errors
def handle_error(e):
    print('SocketIO Error:', e)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5050)
