from flask import Flask, render_template
from flask_socketio import SocketIO
import random
import socket
import threading
import pickle
import time

import utils
import config

config.init()

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
    prompt_text = {
        "en": "Say a short wise message as a robot dog. It should be funny and cute.",
        "hu": "Mondj egy rövid, bölcs üzenetet robotkutyaként. Legyen vicces és aranyos."
    }
    funny = utils.prompt(prompt_text)
    if config.needs_translation():
        funny = utils.translate(funny, config.get_prompt_language())

    welcome_text = {
        "en": "Hello. I am Dogi, a robot dog from BME.",
        "hu": "Szia. Dogi vagyok, egy robotkutya a BME-ről."
    }
    welcome_text = utils.select_text(welcome_text, config.get_ui_language(), True)
    wt, d = utils.tts_wav(welcome_text)
    socketio.emit('audio_play', wt)
    time.sleep(d)

    ft, d = utils.tts_wav(funny)
    socketio.emit('audio_play', ft)

    extra = random.choice([
            "Mit mondhatnék, kutya bajom.",
            "Vau. Mindenbe beleugatok.",
            "Kutyavilág ez ám én mondom.",
            "Vauvau sőt vau."
        ])
        
    xextra = random.choice([
            "What can I say, I am a dog.",
            "I am a dog, I bark. Woof, woof.",
            "Happiness is a warm puppy.",
            "It's a dog-eat-dog world.",
            "Live like someone left the gate open."
        ])

    return "", 200

@socketio.on_error()  # Handle socketio errors
def handle_error(e):
    print('SocketIO Error:', e)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=PORT)
