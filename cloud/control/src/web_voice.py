from flask import Flask, render_template
from flask_socketio import SocketIO
import random
import socket
import threading
import pickle

import utils

PORT = 5052

app = Flask(__name__)

socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*")

# Open UDP socket on port 5004 to receive action events
udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_socket.bind(('0.0.0.0', PORT))

def listen_for_actions():
    while True:
        data, addr = udp_socket.recvfrom(1024)
        action = pickle.loads(data)
        print('Received action:', action)

        if action.get('action') == 'play':
            socketio.emit('audio_play', action.get('data'))

# Create and start the listener thread
listener_thread = threading.Thread(target=listen_for_actions)
listener_thread.start()


@app.route('/')
def index():
    # A special index page
    # 1. connection with socket.io
    # 2. a button to make interaction needed to play background audio
    return render_template('web_voice.html')

@app.route('/init')
def test():
    wf = None
    if utils.get_language() == "Hungarian":
        extra = random.choice([
            "Mit mondhatnék, kutya bajom.",
            "Vau. Mindenbe beleugatok.",
            "Kutyavilág ez ám én mondom.",
            "Vauvau sőt vau."
        ])
        wf, len = utils.tts_wav("Hello. Dogi vagyok, egy robotkutya a BME-ről. " + extra)
    else:
        extra = random.choice([
            "What can I say, I am a dog.",
            "I am a dog, I bark. Woof, woof.",
            "Happiness is a warm puppy.",
            "It's a dog-eat-dog world.",
            "Live like someone left the gate open."
        ])
        xtext = utils.translate("Hello. I am Dogi, a robot dog from BME. " + extra)
        wf, len = utils.tts_wav(xtext)

    socketio.emit('audio_play', wf)
    return "", 200

@socketio.on_error()  # Handle socketio errors
def handle_error(e):
    print('SocketIO Error:', e)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=PORT)
