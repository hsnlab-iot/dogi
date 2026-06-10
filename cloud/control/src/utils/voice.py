import os
import requests
import random
import string
import wave
import time
import re
import io
import socketio
import threading

from transformers import VitsModel, AutoTokenizer
import torch
import scipy

import config

import logging

_mms_cache_lock = threading.Lock()
_mms_cached_model_name = None
_mms_cached_model = None
_mms_cached_tokenizer = None


def _get_mms_model_and_tokenizer(model_name):
    global _mms_cached_model_name, _mms_cached_model, _mms_cached_tokenizer

    with _mms_cache_lock:
        if _mms_cached_model_name != model_name:
            model = VitsModel.from_pretrained(model_name)
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            _mms_cached_model = model
            _mms_cached_tokenizer = tokenizer
            _mms_cached_model_name = model_name

        return _mms_cached_model, _mms_cached_tokenizer


def get_voice_file_path(filename):
    return os.path.join(config.get_cache_dir(), 'voice', filename)


def remove_emojis(text):
    """Remove emoji and other problematic Unicode characters that TTS engines don't handle well."""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"
        "\U0001f926-\U0001f937"  # hand gestures
        "\U00010000-\U0010ffff"  # supplementary multilingual plane
        "\u2640-\u2642"          # gender symbols
        "\u2600-\u2B55"          # miscellaneous symbols and pictographs
        "\u200d"                 # zero-width joiner
        "\u23cf"
        "\u23e9"
        "\u231a"
        "\ufe0f"                 # variation selector
        "\u3030"                 # wavy dash
        "]+"
        , flags=re.UNICODE
    )
    return emoji_pattern.sub(r'', text).strip()


def tts_openai_wav(text, params=None, voice=None):
    if not params or len(params) < 3:
        print("TTS OpenAI parameters are missing")
        return None

    tts_api_base = str(params[0] or "").strip()
    tts_voice = voice or params[1]
    tts_model = params[2]

    if not tts_api_base:
        print("TTS OpenAI api_base is not set")
        return None

    payload = {
        "model": tts_model,
        "voice": tts_voice,
        "input": text,
        "response_format": "wav",
    }

    response = requests.post(tts_api_base + "/audio/speech", json=payload)
    if response.status_code != 200:
        print(f"TTS OpenAI request failed with status code {response.status_code}")
        print(response.text)
        return None

    return response.content


def tts_opentts_wav(text, params=None):
    if not params or len(params) < 2:
        print("TTS OpenTTS parameters are missing")
        return None

    tts_api_base = str(params[0] or "").strip()
    tts_voice = params[1]

    if not tts_api_base:
        print("TTS OpenTTS api_base is not set")
        return None

    query = {
        "voice": tts_voice,
        "text": text,
    }

    response = requests.get(tts_api_base, params=query)
    if response.status_code != 200:
        print(f"TTS request failed with status code {response.status_code}")
        return None
    return response.content


def tts_mms_wav(text, params=None):
    model_name = params[2] if params and len(params) > 2 and params[2] else "facebook/mms-tts-hun"
    model, tokenizer = _get_mms_model_and_tokenizer(model_name)
    inputs = tokenizer(text, return_tensors="pt")

    with torch.no_grad():
        output = model(**inputs).waveform.squeeze().numpy()
        # Convert float waveform to PCM int16 so downstream readers expecting PCM can open it.
        output = output.clip(-1.0, 1.0)
        output = (output * 32767.0).astype('int16')
        wav_buffer = io.BytesIO()
        scipy.io.wavfile.write(wav_buffer, rate=model.config.sampling_rate, data=output)
        wav_buffer.seek(0)
        return wav_buffer.read()


def tts_wav(text, filename=None):
    # Clean emojis and problematic characters from text before TTS processing
    text = remove_emojis(text)

    filename_ok = False
    # Check if the file already exists
    if filename and os.path.exists(get_voice_file_path(filename)):
        filename_ok = True

    if not filename_ok:
        params = config.get_tts_parameters()
        tts_voice = params[1]
        tts_model = params[2]
        tts_protocol = params[3]
        print(f"Requesting TTS (protocol={tts_protocol}) with voice: {tts_voice} model: {tts_model} text: {text}")

        wav = None
        now = time.time()
        if tts_protocol == 'openai':
            wav = tts_openai_wav(text, params)
        elif tts_protocol == 'mms':
            wav = tts_mms_wav(text, params)
        elif tts_protocol == 'opentts':
            wav = tts_opentts_wav(text, params)

        print("TTS request time:", time.time() - now)

        # Save the audio file
        if filename is None:
            filename = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10)) + '.wav'
        if not filename.lower().endswith('.wav'):
            filename += '.wav'
        with open(get_voice_file_path(filename), 'wb') as file:
            file.write(wav)
        print(f"Saved to {filename}")

    # Get duration of the WAV file. Python's wave module cannot read IEEE-float WAV (format=3).
    wav_path = get_voice_file_path(filename)
    try:
        with wave.open(wav_path, 'rb') as wav_file:
            num_frames = wav_file.getnframes()
            frame_rate = wav_file.getframerate()
    except wave.Error:
        frame_rate, samples = scipy.io.wavfile.read(wav_path)
        num_frames = samples.shape[0]

    return filename, num_frames / frame_rate


def play_wav(filename):

    if not filename.lower().endswith('.wav'):
        filename += '.wav'

    voice_port = config.get_voice_port()
    sio = socketio.Client()
    try:
        sio.connect(f'http://localhost:{voice_port}')
        sio.emit('audio_play_proxy', filename)
        sio.sleep(0.2)
    except Exception as e:
        print(f'Cannot use socketio: {e}')
    finally:
        sio.disconnect()
