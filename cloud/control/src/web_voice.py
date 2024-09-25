from flask import Flask, render_template
from flask_socketio import SocketIO
import socket
import threading
import requests
import random
import string
import ollama
import os
import wave

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
    # Get duration of the the WAV file
    with wave.open('static/' + filename, 'rb') as wav_file:
        num_frames = wav_file.getnframes()
        frame_rate = wav_file.getframerate()
    return num_frames / frame_rate

def trans_function(text):
    print("Requesting translation with text: ", text)
    hutext = ollama_client.generate(model='llama3.1', 
        prompt='Translate the following sentence or word from English to Hungarian.' \
            'Do not say anything else, just the Hungarian translation. ' \
            'The English text is: ' + str(text),
            stream=False)
    print("Respomse: ", hutext['response'])
    length = tts_function(hutext['response'])
    return (length, hutext['response'])

# receive TTS requests from UDP
def receive_tts_tcp():
    tcp_socket_tts.listen(1)
    while True:
        client_socket_tts, addr_tts = tcp_socket_tts.accept()
        data_tts = client_socket_tts.recv(1024)
        length = tts_function(data_tts)
        client_socket_tts.sendall(str(length).encode())
        client_socket_tts.close()

# Receive translation requests from UDP
def receive_trans_tcp():
    tcp_socket_trans.listen(1)
    while True:
        client_socket_trans, addr_trans = tcp_socket_trans.accept()
        data_trans = client_socket_trans.recv(1024)
        (length, hutext) = trans_function(data_trans)
        response = str(length) + ":" + hutext
        client_socket_trans.sendall(response.encode('utf-8'))
        client_socket_trans.close()

# Start the TCP socket listeners in a separate threads
tcp_socket_tts = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp_socket_tts.bind(('0.0.0.0', 5010))
tcp_thread_tts = threading.Thread(target=receive_tts_tcp)
tcp_thread_tts.start()

tcp_socket_trans = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp_socket_trans.bind(('0.0.0.0', 5011))
tcp_thread_trans = threading.Thread(target=receive_trans_tcp)
tcp_thread_trans.start()


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
    d = tts_function("Hello. Dogi vagyok, egy robotkutya a BME-ről. " + text)
    print(text)
    print(d)
    return "", 200

@socketio.on_error()  # Handle socketio errors
def handle_error(e):
    print('SocketIO Error:', e)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5052)
