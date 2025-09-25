import os
import socket
import ollama

DEFAULT_MODEL = 'gemma3:12b-it-qat'

DEFAULT_VOICE_PORT = 5052
DEFAULT_CONTROL_PORT = 5002

def init():
    """Initialize configuration by calling all singleton functions."""
    get_ui_language()
    get_prompt_language()
    get_translation_model()
    get_ollama_client()
    get_tts_engine_and_voice()
    get_voice_socket()
    get_control_socket()


def get_ui_language():
    """Singleton to ensure get_language stays in memory."""
    if not hasattr(get_ui_language, "_language"):
        language = os.environ.get('TRANSLATION', '0')
        if language == '0':
            get_ui_language._language = None
            print("Translation is disabled")
        else:
            get_ui_language._language = language
            print (f"Using language: {get_ui_language._language}")

    return get_ui_language._language

def get_prompt_language():
    """Singleton to ensure prompt_language stays in memory."""
    if not hasattr(get_prompt_language, "_prompt_language"):
        prompt_language = os.environ.get('PROMPT_LANGUAGE', 'en')
        get_prompt_language._prompt_language = prompt_language
        print (f"Using prompt language: {get_prompt_language._prompt_language}")

    return get_prompt_language._prompt_language

def needs_translation():
    """Check if translation is needed based on UI language."""
    need1 = get_ui_language() is not None
    need2 = get_ui_language() != get_prompt_language()
    return need1 and need2

def get_general_model():
    """Singleton to ensure general_model stays in memory."""
    if not hasattr(get_general_model, "_generalmodel"):
        general_model = os.environ.get('MODEL', DEFAULT_MODEL)
        get_general_model._generalmodel = general_model
    return get_general_model._generalmodel

def get_translation_model():
    """Singleton to ensure translation_model stays in memory."""
    if not hasattr(get_translation_model, "_model"):
        translation_model = os.environ.get('TRANSLATION_MODEL', get_general_model())
        get_translation_model._model = translation_model
    return get_translation_model._model

def get_vision_model():
    """Singleton to ensure vision_model stays in memory."""
    if not hasattr(get_vision_model, "_visionmodel"):
        vision_model = os.environ.get('VISION_MODEL', get_general_model())
        get_vision_model._visionmodel = vision_model
    return get_vision_model._visionmodel

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
