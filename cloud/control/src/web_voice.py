from flask import Flask, render_template
from flask_socketio import SocketIO
import socket
import threading
import requests
import random
import string
import ollama
import os

app = Flask(__name__)

socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*")

ollama_ip = os.environ.get('OLLAMA_IP')
if ollama_ip is None:
    raise ValueError('OLLAMA_IP environment variable is not set')

tts_ip = os.environ.get('TTS_IP')
if tts_ip is None:
    raise ValueError('TTS_IP environment variable is not set')

ollama_client = ollama.Client(host=f'http://{ollama_ip}:11434')

def tts_function(text):
    voice = "hu_diana_majlinger"
    params = {
        "voice": voice,
        "text": text
    }
    print("Requesting TTS with text: ", text)
    response = requests.get(f"http://{tts_ip}:5500/api/tts", params=params)
    #print("Response: ", response.content)

    # Save the audio file
    filename = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10)) + '.wav'
    with open('static/' + filename, 'wb') as file:
        file.write(response.content)
    # Notify the client to download and play the audio
    socketio.emit('audio_play', filename)

def trans_function(text):
    print("Requesting translation with text: ", text)
    hutext = ollama_client.generate(model='llama3.1', 
        prompt='Translate the following sentence or word from English to Hungarian.' \
            'Do not say anything else, just the Hungarian translation. ' \
            'The English text is: ' + str(text),
            stream=False)
    print("Respomse: ", hutext['response'])
    tts_function(hutext['response'])

# receive TTS requests from UDP
def receive_tts_udp():
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind(('0.0.0.0', 5010))

    while True:
        data, addr = udp_socket.recvfrom(1024)
        tts_function(data)

# Receive translation requests from UDP
def receive_trans_udp():
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind(('0.0.0.0', 5011))

    while True:
        data, addr = udp_socket.recvfrom(1024)
        trans_function(data)

# Start the UDP socket listeners in a separate threads
udp_thread_tts = threading.Thread(target=receive_tts_udp)
udp_thread_tts.start()

udp_thread_trans = threading.Thread(target=receive_trans_udp)
udp_thread_trans.start()


@app.route('/')
def index():
    # A special index page
    # 1. connection with socket.io
    # 2. a button to make interaction needed to play background audio
    return render_template('web_voice.html')

@app.route('/test')
def test():
    #data = "vauvau.wav"
    #socketio.emit('audio_play', data)
    text = random.choice([
        "Mit mondhatnék, kutya bajom.",
        "Mindenbe beleugatok.",
        "Kutyavilág ez án mondom.",
        "Vauvau sőt vau."
    ])
    tts_function("Hello. Dogi vagyok, egy robotkutya a BME-ről. " + text)
    return "", 200

@socketio.on_error()  # Handle socketio errors
def handle_error(e):
    print('SocketIO Error:', e)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5040)
