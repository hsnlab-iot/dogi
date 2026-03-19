import os
import json
import requests
import random
import string
import wave
import socket
import pickle
import time
import base64
import mimetypes
from transformers import pipeline
import re

import config

language_longname = {
    'af': 'Afrikaans', 'am': 'Amharic', 'an': 'Aragonese',
    'ar': 'Arabic', 'as': 'Assamese', 'az': 'Azerbaijani',
    'be': 'Belarusian', 'bg': 'Bulgarian', 'bn': 'Bengali',
    'br': 'Breton', 'bs': 'Bosnian', 'ca': 'Catalan',
    'cs': 'Czech', 'cy': 'Welsh', 'da': 'Danish',
    'de': 'German', 'dz': 'Dzongkha', 'el': 'Greek',
    'en': 'English', 'eo': 'Esperanto', 'es': 'Spanish',
    'et': 'Estonian', 'eu': 'Basque', 'fa': 'Persian',
    'fi': 'Finnish', 'fr': 'French', 'fy': 'Western Frisian',
    'ga': 'Irish', 'gd': 'Scottish Gaelic', 'gl': 'Galician',
    'gu': 'Gujarati', 'ha': 'Hausa', 'he': 'Hebrew',
    'hi': 'Hindi', 'hr': 'Croatian', 'it': 'Italian',
    'hu': 'Hungarian', 'hy': 'Armenian', 'id': 'Indonesian',
    'ig': 'Igbo', 'is': 'Icelandic', 'ja': 'Japanese',
    'ka': 'Georgian', 'kk': 'Kazakh', 'km': 'Khmer',
    'kn': 'Kannada', 'ko': 'Korean', 'ku': 'Kurdish',
    'ky': 'Kyrgyz', 'li': 'Limburgish', 'lt': 'Lithuanian',
    'lv': 'Latvian', 'mg': 'Malagasy', 'mk': 'Macedonian',
    'ml': 'Malayalam', 'mn': 'Mongolian', 'mr': 'Marathi',
    'ms': 'Malay', 'mt': 'Maltese', 'my': 'Burmese',
    'nb': 'Norwegian Bokmal', 'ne': 'Nepali', 'nl': 'Dutch',
    'nn': 'Norwegian Nynorsk', 'no': 'Norwegian', 'oc': 'Occitan',
    'or': 'Odia', 'pa': 'Punjabi', 'pl': 'Polish',
    'ps': 'Pashto', 'pt': 'Portuguese', 'ro': 'Romanian',
    'ru': 'Russian', 'rw': 'Kinyarwanda', 'se': 'Northern Sami',
    'sh': 'Serbo-Croatian', 'si': 'Sinhala', 'sk': 'Slovak',
    'sl': 'Slovenian', 'sq': 'Albanian', 'sr': 'Serbian',
    'sv': 'Swedish', 'ta': 'Tamil', 'te': 'Telugu',
    'tg': 'Tajik', 'th': 'Thai', 'tk': 'Turkmen',
    'tr': 'Turkish', 'tt': 'Tatar', 'ug': 'Uyghur',
    'uk': 'Ukrainian', 'ur': 'Urdu', 'uz': 'Uzbek',
    'vi': 'Vietnamese', 'wa': 'Walloon', 'xh': 'Xhosa',
    'yi': 'Yiddish', 'yo': 'Yoruba', 'zh': 'Chinese',
    'zu': 'Zulu'
}

def lang_short(lang):
    if lang in language_longname:
        return lang
    for short, long in language_longname.items():
        if lang.lower() == long.lower():
            return short
    return None

def lang_long(lang):
    if lang in language_longname:
        return language_longname[lang]
    for short, long in language_longname.items():
        if lang.lower() == short.lower():
            return long
    return None


def debug_openai_request(tag, request_kwargs):
    try:
        serialized = json.dumps(request_kwargs, ensure_ascii=False, indent=2)
    except TypeError:
        serialized = str(request_kwargs)

    print(f"[DEBUG][OpenAI][{tag}] request args:\n{serialized}")


def debug_openai_response(tag, response):
    payload = None

    try:
        payload = response.model_dump()
    except Exception:
        pass

    if payload is None:
        try:
            payload = response.to_dict()
        except Exception:
            pass

    if payload is None:
        try:
            payload = json.loads(response.model_dump_json())
        except Exception:
            payload = str(response)

    try:
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    except TypeError:
        serialized = str(payload)

    print(f"[DEBUG][OpenAI][{tag}] response:\n{serialized}")

def translate(text, src_lang, tgt_lang = config.get_ui_language()):
    
    src_long = lang_long(src_lang)
    tgt_long = lang_long(tgt_lang)
    print(f"Requesting translation from {src_long} to {tgt_long} with text: {text}")

    if tgt_lang == None: # No translation required
        print(f"No target language specified, skipping translation. Returning original text.")
        return text
    
    if tgt_lang == src_lang: # No translation needed
        print(f"Source and target languages are the same ({src_lang}), skipping translation. Returning original text.")
        return text
 
    translation_model = config.get_translation_model()
    if translation_model == 'opus':
        return translate_opus(text, src_lang, tgt_lang)  

    openai_client = config.get_openai_client()

    now = time.time()
    request_kwargs = {
        "model": translation_model,
        "messages": [
            {"role": "system", "content": 
                "You are a professional, high-fidelity translator."
                "Rules:"
                "1. Output ONLY the translated text."
                f"2. Translate the input text accurately from {src_long} to {tgt_long}."
                "3. Preserve the original tone, formatting (Markdown/HTML), and intent."
                "4. Do NOT provide explanations, notes, or introductory text."
            },
            {"role": "user", "content":
             f"Translate from {src_long} to {tgt_long}:"
             f"{text}"
            }
        ],
        "temperature": 0.1,
        "max_tokens": config.get_openai_translation_max_output_tokens(),
    }
    debug_openai_request("translate", request_kwargs)
    response = openai_client.chat.completions.create(**request_kwargs)
    debug_openai_response("translate", response)
    print(f"OpenAI ({translation_model}) translation time:", time.time() - now)
    return response.choices[0].message.content

def translate_opus(text, src_lang, tgt_lang = config.get_ui_language()):
    if src_lang is None or tgt_lang is None:
        print("Source or target language not found")
        return text

    short_src = lang_short(src_lang)
    long_src = lang_long(src_lang)
    short_tgt = lang_short(tgt_lang)
    long_tgt = lang_long(tgt_lang)
    model_name = f"Helsinki-NLP/opus-mt-tc-big-{short_src}-{short_tgt}"
    translator = pipeline(f"translation_{short_src}_to_{short_tgt}", model=model_name)
    # Check pipeline if exists, if not return original text
    if translator is None:
        print(f"Opus translation pipeline not found for {long_src} ({short_src}) to {long_tgt} ({short_tgt})")
        return text

    # Opus models can struggle with long texts, so we split into smaller chunks if needed
    now = time.time()

    def split_text_into_chunks(text, max_length=200):
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current_chunk = ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= max_length:
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
        if current_chunk:
            chunks.append(current_chunk.strip())
        return chunks
    chunks = split_text_into_chunks(text)

    xchunks = []
    for c in chunks:
        xchunks.append(translator(c)[0]['translation_text'])
    xtext = ' '.join(xchunks)
    print("Opus translation time:", time.time() - now)
    #print(f"translation: {xtext}")
    return xtext

def prompt(prompt_text, images = None, stream = False):
    def _reasoning_to_text(reasoning_value):
        if not reasoning_value:
            return ""

        if isinstance(reasoning_value, str):
            return reasoning_value

        if isinstance(reasoning_value, list):
            parts = []
            for item in reasoning_value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
                else:
                    text = getattr(item, "text", None) or getattr(item, "content", None)
                    if isinstance(text, str):
                        parts.append(text)
            return ''.join(parts)

        if isinstance(reasoning_value, dict):
            text = reasoning_value.get("text") or reasoning_value.get("content")
            if isinstance(text, str):
                return text

        text = getattr(reasoning_value, "text", None) or getattr(reasoning_value, "content", None)
        if isinstance(text, str):
            return text

        return str(reasoning_value)

    if isinstance(prompt_text, dict):
        prompt_text = select_text(prompt_text, config.get_prompt_language())

    soul_prompt = config.get_soul_content()

    model = None

    if images:
        print(f"Prompting with{' stream' if stream else ''}: {prompt_text} and {len(images)} images")
    else:
        print(f"Prompting with{' stream' if stream else ''}: {prompt_text}")

    if images:
        model = config.get_vision_model()
    else:
        model = config.get_general_model()

    openai_client = config.get_openai_client()
    now = time.time()
    
    # Build message content
    content = [{"type": "text", "text": prompt_text}]
    
    if images:
        for image in images:
            # If image is a file path, read and encode as base64
            if isinstance(image, str) and not image.startswith('data:'):
                try:
                    with open(image, 'rb') as f:
                        image_data = base64.standard_b64encode(f.read()).decode('utf-8')
                    # Determine mime type
                    mime_type, _ = mimetypes.guess_type(image)
                    if mime_type is None:
                        mime_type = 'image/jpeg'
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_data}"}
                    })
                except (FileNotFoundError, IOError) as e:
                    print(f"Warning: Could not load image {image}: {e}")
            else:
                # Assume it's already base64 encoded data URL
                content.append({
                    "type": "image_url",
                    "image_url": {"url": image}
                })

    request_kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": soul_prompt},
            {"role": "user", "content": content},
            {"role": "assistant", "content": "<think></think>"}
        ],
        "temperature": config.get_openai_prompt_temperature(),
        "frequency_penalty": config.get_openai_prompt_frequency_penalty(),
        "max_tokens": config.get_openai_max_output_tokens(),
    }

    if stream:
        request_kwargs["stream"] = True

    request_kwargs["extra_body"] = config.get_openai_general_extra_body(
        num_predict=config.get_openai_max_output_tokens()
    )

    thinking_enabled_config = config.get_openai_enable_thinking()
    thinking_enabled_sent = bool(request_kwargs.get("extra_body", {}).get("enable_thinking"))
    if thinking_enabled_config and thinking_enabled_sent:
        print("enable_thinking is active for this prompt request")
    elif thinking_enabled_config and not thinking_enabled_sent:
        print("Warning: enable_thinking is enabled in config but not sent for this prompt request")
    else:
        print("enable_thinking is disabled in config")

    debug_openai_request("prompt", request_kwargs)

    if stream:
        stream_response = openai_client.chat.completions.create(**request_kwargs)
        full_response_parts = []
        full_reasoning_parts = []
        finish_reason = None
        usage = None
        reasoning_header_printed = False

        print("Streamed response:", end=" ", flush=True)
        for chunk in stream_response:
            if getattr(chunk, "usage", None) is not None:
                usage = chunk.usage

            if not getattr(chunk, "choices", None):
                continue

            choice = chunk.choices[0]
            delta = getattr(choice, "delta", None)
            piece = getattr(delta, "content", None) if delta is not None else None
            reasoning_piece = getattr(delta, "reasoning_content", None) if delta is not None else None

            reasoning_text = _reasoning_to_text(reasoning_piece)
            if reasoning_text:
                if not reasoning_header_printed:
                    print("\nStreamed reasoning:", end=" ", flush=True)
                    reasoning_header_printed = True
                print(reasoning_text, end="", flush=True)
                full_reasoning_parts.append(reasoning_text)

            if piece:
                if reasoning_header_printed:
                    print("\nStreamed response:", end=" ", flush=True)
                    reasoning_header_printed = False
                print(piece, end="", flush=True)
                full_response_parts.append(piece)

            if getattr(choice, "finish_reason", None) is not None:
                finish_reason = choice.finish_reason

        print()

        if finish_reason is not None:
            print(f"Finish Reason: {finish_reason}")
        if usage is not None:
            print(f"Usage: {usage}")
        if full_reasoning_parts:
            print(f"Reasoning: {''.join(full_reasoning_parts)}")
        print(f"OpenAI ({model}) prompt stream time: {time.time() - now}")

        filtered_response = response_filter(''.join(full_response_parts))

    else:

        response = openai_client.chat.completions.create(**request_kwargs)
        print(f"Finish Reason: {response.choices[0].finish_reason}")
        print(f"Usage: {response.usage}")
        debug_openai_response("prompt", response)
        reasoning_text = _reasoning_to_text(getattr(response.choices[0].message, "reasoning_content", None))
        if reasoning_text:
            print(f"Reasoning: {reasoning_text}")
        filtered_response = response_filter(response.choices[0].message.content)
    
    print(f"OpenAI ({model}) prompt time: {time.time() - now}")
    return filtered_response

def response_filter(response):
    # Remove any leading/trailing whitespace and unwanted characters
    response = response.strip()

    # Remove bold text marked with **, and followed by a ":"
    response = re.sub(r'\*\*[^*]+:\*\*', '', response)  # Remove bold text followed by ":"
    
    # Remove list markers that are a star with 3 spaces
    response = re.sub(r'^\s*\*\s{3}', '', response, flags=re.MULTILINE)

    # Remove all ** around words
    response = re.sub(r'\*\*(.*?)\*\*', r'\1', response)

    return response


def get_voice_file_path(filename):
    return os.path.join(config.get_voice_cache_dir(), filename)

def tts_wav(text, filename = None):
    filename_ok = False
     # Check if the file already exists
    if filename and os.path.exists(get_voice_file_path(filename)):
        filename_ok = True

    if not filename_ok:
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
        if filename is None:
            filename = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10)) + '.wav'
        if not filename.lower().endswith('.wav'):
            filename += '.wav'
        with open(get_voice_file_path(filename), 'wb') as file:
            file.write(response.content)

    # Get duration of the the WAV file
    with wave.open(get_voice_file_path(filename), 'rb') as wav_file:
        num_frames = wav_file.getnframes()
        frame_rate = wav_file.getframerate()

    return filename, num_frames / frame_rate

def play_wav(filename):
    if not filename.lower().endswith('.wav'):
        filename += '.wav'
    sock = config.get_voice_socket()
    sock.send(pickle.dumps({'action': 'play', 'data': filename}))

def select_text(text_dict, language, do_translate = False):
    if lang_short(language) in text_dict:
        return text_dict[lang_short(language)]
    elif lang_long(language) in text_dict:
        return text_dict[lang_long(language)]

    # If exact language not found, try English version as fallback, with optional translation
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
            return translate(first_item, first_lang, language) # First item

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
