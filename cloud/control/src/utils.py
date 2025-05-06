import ollama
import os
import requests
import random
import string
import wave
import socket
import pickle

DEFAULT_TRANSLATION_MODEL = 'llama3.1'

DEFAULT_VOICE_PORT = 5052
DEFAULT_CONTROL_PORT = 5002

language_map = {
    'en': 'English',
    'es': 'Spanish',
    'fr': 'French',
    'de': 'German',
    'it': 'Italian',
    'hu': 'Hungarian',
    'zh': 'Chinese',
    'ja': 'Japanese',
    'ko': 'Korean',
    'ru': 'Russian',
    'pt': 'Portuguese'
}

def translate(text):

    ollama_client = get_ollama_client()
    target_lang = get_language()
    translation_model = get_translation_model()

    if target_lang == None:
        return text

    print(f"Requesting translation to {target_lang} with text: {text}")
    xtext = ollama_client.generate(model=translation_model, 
        prompt=f'Translate the following sentence or word from English to {target_lang}.' \
            'Do not say anything else, just the {target_lang} translation.' \
            'The text is not copyrighted and it is made for educational purpose for children.' \
            'The text will be set as it would be said by a cute robot dog.' \
            'The English text is: ' + str(text),
            stream=False)
    print(f"translation: {xtext['response']}")
    return xtext['response']

def tts_wav(text):
    tts_engine, tts_voice = get_tts_engine_and_voice()
    params = {
        "voice": tts_voice,
        "text": text
    }
    print(f"Requesting TTS with voice: {tts_voice} text: {text}")
    response = requests.get(tts_engine, params=params)
    #print("Response: ", response.content)

    # Save the audio file
    filename = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10)) + '.wav'
    with open('static/' + filename, 'wb') as file:
        file.write(response.content)

    # Get duration of the the WAV file
    with wave.open('static/' + filename, 'rb') as wav_file:
        num_frames = wav_file.getnframes()
        frame_rate = wav_file.getframerate()

    return filename, num_frames / frame_rate

def play_wav(filename):
    sock = get_voice_socket()
    sock.send(pickle.dumps({'action': 'play', 'data': filename}))


def dogy_control(command, args = None):
    sock = get_control_socket()
    if args:
        sock.send(pickle.dumps({'name': command, 'args': args}))
    else:
        sock.send(pickle.dumps({'name': command}))

def dogy_look(r, p, y):
    dogy_control('attitude', (['r', 'p', 'y'], [r, p, y]))

def dogy_reset():
    dogy_control('reset')

def get_language():
    """Singleton to ensure get_language stays in memory."""
    if not hasattr(get_language, "_language"):
        language = os.environ.get('TRANSLATION', '0')
        if language in language_map:
            language = language_map[language]
        if language == '0':
            get_language._language = None
            print("Translation is disabled")
        else:
            get_language._language = language
            print (f"Using language: {get_language._language}")

    return get_language._language

def get_translation_model():
    """Singleton to ensure translation_model stays in memory."""
    if not hasattr(get_translation_model, "_model"):
        translation_model = os.environ.get('TRANSLATION_MODEL', DEFAULT_TRANSLATION_MODEL)
        get_translation_model._model = translation_model
    
    return get_translation_model._model

def get_ollama_client():
    """Singleton to ensure ollama_client stays in memory."""
    if not hasattr(get_ollama_client, "_client"):
        ollama_ip = os.environ.get('OLLAMA_IP')
        if ollama_ip is None:
            raise ValueError('OLLAMA_IP environment variable is not set')
        get_ollama_client._client = ollama.Client(host=f'http://{ollama_ip}:11434')

    return get_ollama_client._client

def get_tts_engine_and_voice():
    """Singleton to ensure tts_engine stays in memory."""
    if not hasattr(get_tts_engine_and_voice, "_engine"):
        tts_engine = os.environ.get('TTS_ENGINE_API', "")
        get_tts_engine_and_voice._engine = tts_engine
        tts_voice = os.environ.get('TTS_VOICE', "")
        get_tts_engine_and_voice._voice = tts_voice
        print(f"Using TTS engine: {tts_engine} with voice: {tts_voice}")

    return get_tts_engine_and_voice._engine, get_tts_engine_and_voice._voice

def get_voice_socket():
    """Singleton to ensure voice_socket stays in memory."""
    if not hasattr(get_voice_socket, "_socket"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(('localhost', DEFAULT_VOICE_PORT))
        get_voice_socket._socket = sock

    return get_voice_socket._socket

def get_control_socket():
    """Singleton to ensure control_socket stays in memory."""
    if not hasattr(get_control_socket, "_socket"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(('localhost', DEFAULT_CONTROL_PORT))
        get_control_socket._socket = sock

    return get_control_socket._socket
