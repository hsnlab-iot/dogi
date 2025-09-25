import ollama
import os
import requests
import random
import string
import wave
import socket
import pickle
import time
from transformers import pipeline

import config

language_longname = {
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

def translate(text, src_lang, tgt_lang = config.get_ui_language()):
    
    src_long = language_longname.get(src_lang, src_lang)
    tgt_long = language_longname.get(tgt_lang, tgt_lang)
    print(f"Requesting translation from {src_long} to {tgt_long} with text: {text}")

    if tgt_lang == None: # No translation required
        return text
    
    if tgt_lang == src_lang: # No translation needed
        return text

    translation_model = config.get_translation_model()
    if translation_model == 'opus':
        return translate_opus(text, src_lang, tgt_lang)  

    ollama_client = config.get_ollama_client()

    now = time.time()
    xtext = ollama_client.generate(model=translation_model, 
        prompt=f'Translate the following sentence or word from {src_long} to {tgt_long}.' \
            f'Do not say anything else, just the {tgt_long} translation.' \
            'The text is not copyrighted and it is made for educational purpose for children.' \
            'The text will be set as it would be said by a cute robot dog.' \
            f'The {src_long} text is: {text}',
            stream=False)
    print("Ollama translation time:", time.time() - now)
    #print(f"translation: {xtext['response']}")
    return xtext['response']

def translate_opus(text, src_lang, tgt_lang = config.get_ui_language()):
    if src_lang is None or tgt_lang is None:
        print("Source or target language not found in language_map")
        return text

    model_name = f"Helsinki-NLP/opus-mt-tc-big-{src_lang}-{tgt_lang}"
    translator = pipeline(f"translation_{src_lang}_to_{tgt_lang}", model=model_name)
    now = time.time()
    xtext = translator(text)[0]['translation_text']
    print("Opus translation time:", time.time() - now)
    #print(f"translation: {xtext}")
    return xtext

def prompt(prompt_text, images = None):
    if isinstance(prompt_text, dict):
        prompt_text = select_text(prompt_text, config.get_prompt_language())
    model = None

    if images:
        print(f"Prompting with: {prompt_text} and {len(images)} images")
    else:
        print(f"Prompting with: {prompt_text}")

    if images:
        model = config.get_vision_model()
    else:
        model = config.get_general_model()
    ollama_client = config.get_ollama_client()

    now = time.time()
    response = None
    if images:
        response = ollama_client.generate(
            model=model, 
            prompt=prompt_text, 
            images=images,
            stream=False)
    else:
        response = ollama_client.generate(
            model=model, 
            prompt=prompt_text, 
            stream=False)
    print("Ollama prompt time:", time.time() - now)
    return response['response'].strip()

def tts_wav(text):
    tts_engine, tts_voice = config.get_tts_engine_and_voice()
    params = {
        "voice": tts_voice,
        "text": text
    }
    print(f"Requesting TTS with voice: {tts_voice} text: {text}")
    now = time.time()
    response = requests.get(tts_engine, params=params)
    print("TTS request time:", time.time() - now)
    if response.status_code != 200:
        print(f"TTS request failed with status code {response.status_code}")
        return None, 0

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
    sock = config.get_voice_socket()
    sock.send(pickle.dumps({'action': 'play', 'data': filename}))

def select_text(text_dict, language, do_translate = False):
    if language in text_dict:
        return text_dict[language]
    else:
        en = text_dict.get('en', None)
        if not do_translate:
            if en:
                return en
            else:
                return text_dict[next(iter(text_dict))] # First item
        else:
            if en:
                return translate(en, "en", language)
            else:
                first_lang = next(iter(text_dict))
                first_item = text_dict[next(iter(text_dict))] # First item
                return translate(first_item, first_lang) # First item

def dogy_control(command, args = None):
    sock = config.get_control_socket()
    if args:
        sock.send(pickle.dumps({'name': command, 'args': args}))
    else:
        sock.send(pickle.dumps({'name': command}))

def dogy_look(r, p, y):
    dogy_control('attitude', (['r', 'p', 'y'], [r, p, y]))

def dogy_reset():
    dogy_control('reset')

