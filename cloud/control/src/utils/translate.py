import re
import time
from transformers import pipeline

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


def _debug_openai_request(tag, request_kwargs):
    import json
    try:
        serialized = json.dumps(request_kwargs, ensure_ascii=False, indent=2)
    except TypeError:
        serialized = str(request_kwargs)

    print(f"[DEBUG][OpenAI][{tag}] request args:\n{serialized}")


def _debug_openai_response(tag, response):
    import json
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


def translate_opus(text, src_lang, tgt_lang=config.get_ui_language()):
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
    return xtext


def translate(text, src_lang, tgt_lang=config.get_ui_language()):
    src_long = lang_long(src_lang)
    tgt_long = lang_long(tgt_lang)
    print(f"Requesting translation from {src_long} to {tgt_long} with text: {text}")

    if tgt_lang == None:  # No translation required
        print(f"No target language specified, skipping translation. Returning original text.")
        return text

    if tgt_lang == src_lang:  # No translation needed
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
    _debug_openai_request("translate", request_kwargs)
    response = openai_client.chat.completions.create(**request_kwargs)
    _debug_openai_response("translate", response)
    print(f"OpenAI ({translation_model}) translation time:", time.time() - now)
    return response.choices[0].message.content
