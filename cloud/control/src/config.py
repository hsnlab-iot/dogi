import os
import socket
import importlib

try:
    tomllib = importlib.import_module('tomllib')
except ModuleNotFoundError:
    tomllib = importlib.import_module('tomli')

DEFAULT_MODEL = 'qwen3.5'
DEFAULT_UI_LANG = 'en'
DEFAULT_PROMPT_LANG = 'en'
DEFAULT_OPENAI_API_BASE = 'http://localhost:11434/v1'
DEFAULT_OPENAI_API_KEY = 'not-needed'
DEFAULT_OPENAI_KEEP_ALIVE = '30m'
DEFAULT_OPENAI_ENABLE_THINKING = True
DEFAULT_OPENAI_THINKING_BUDGET = 500
DEFAULT_OPENAI_MAX_OUTPUT_TOKENS = 512
DEFAULT_OPENAI_TRANSLATION_MAX_OUTPUT_TOKENS = 1024
DEFAULT_OPENAI_PROMPT_TEMPERATURE = 0.3
DEFAULT_OPENAI_PROMPT_FREQUENCY_PENALTY = 1.5
DEFAULT_TRANSLATION_MODEL = 'opus'
DEFAULT_VISION_MODEL = ''
DEFAULT_TTS_ENGINE = ''
DEFAULT_TTS_VOICE = ''
DEFAULT_VOICE_CACHE_DIR = '~/.cache/voice'

DEFAULT_VOICE_PORT = 5052
DEFAULT_CONTROL_PORT = 5002

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
CONTROL_DIR = os.path.dirname(SRC_DIR)
CONFIG_DIR = os.path.join(CONTROL_DIR, 'config')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.toml')

_config_data = None
_openai_client = None
_voice_socket = None
_control_socket = None
_ui_language = None
_prompt_language = None
_general_model = None
_translation_model = None
_vision_model = None
_openai_keep_alive = None
_openai_enable_thinking = None
_openai_thinking_budget = None
_openai_max_output_tokens = None
_openai_translation_max_output_tokens = None
_openai_prompt_temperature = None
_openai_prompt_frequency_penalty = None
_tts_engine = None
_tts_voice = None
_voice_cache_dir = None
_soul_language = None
_soul_content = None


def _build_default_config():
    return {
        'language': {
            'ui': DEFAULT_UI_LANG,
            'prompt': DEFAULT_PROMPT_LANG,
        },
        'models': {
            'general': DEFAULT_MODEL,
            'vision': DEFAULT_VISION_MODEL,
            'translation': DEFAULT_TRANSLATION_MODEL,
        },
        'openai': {
            'api_base': DEFAULT_OPENAI_API_BASE,
            'api_key': DEFAULT_OPENAI_API_KEY,
            'keep_alive': DEFAULT_OPENAI_KEEP_ALIVE,
            'enable_thinking': DEFAULT_OPENAI_ENABLE_THINKING,
            'thinking_budget': DEFAULT_OPENAI_THINKING_BUDGET,
            'max_output_tokens': DEFAULT_OPENAI_MAX_OUTPUT_TOKENS,
            'translation_max_output_tokens': DEFAULT_OPENAI_TRANSLATION_MAX_OUTPUT_TOKENS,
            'prompt_temperature': DEFAULT_OPENAI_PROMPT_TEMPERATURE,
            'prompt_frequency_penalty': DEFAULT_OPENAI_PROMPT_FREQUENCY_PENALTY,
        },
        'tts': {
            'engine_api': DEFAULT_TTS_ENGINE,
            'voice': DEFAULT_TTS_VOICE,
            'cache_dir': DEFAULT_VOICE_CACHE_DIR,
        },
        'ports': {
            'voice': DEFAULT_VOICE_PORT,
            'control': DEFAULT_CONTROL_PORT,
        },
    }


def _merge_dict(base, override):
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _normalize_lang(raw_lang, fallback):
    normalized = str(raw_lang or fallback).strip().lower().replace('_', '-')
    if '-' in normalized:
        normalized = normalized.split('-')[0]
    if len(normalized) < 2:
        normalized = fallback
    return normalized[:2]


def _load_config_file():
    defaults = _build_default_config()
    with open(CONFIG_PATH, 'rb') as f:
        loaded = tomllib.load(f)
    return _merge_dict(defaults, loaded)


def get_config_data():
    global _config_data

    if _config_data is None:
        _config_data = _load_config_file()

    return _config_data


def _get_config_value(section, key, default=None):
    section_data = get_config_data().get(section, {})
    return section_data.get(key, default)


def _close_socket(sock):
    if sock is None:
        return

    try:
        sock.close()
    except OSError:
        pass


def init():
    """Initialize configuration by loading config and priming singletons."""
    get_config_data()
    get_ui_language()
    get_prompt_language()
    get_translation_model()
    get_openai_client()
    get_soul_content()
    get_tts_engine_and_voice()
    get_voice_socket()
    get_control_socket()


def reinit():
    """Reload configuration from disk and rebuild cached clients and sockets."""
    global _config_data
    global _openai_client
    global _voice_socket
    global _control_socket
    global _ui_language
    global _prompt_language
    global _general_model
    global _translation_model
    global _vision_model
    global _openai_keep_alive
    global _openai_enable_thinking
    global _openai_thinking_budget
    global _openai_max_output_tokens
    global _openai_translation_max_output_tokens
    global _openai_prompt_temperature
    global _openai_prompt_frequency_penalty
    global _tts_engine
    global _tts_voice
    global _voice_cache_dir
    global _soul_language
    global _soul_content

    _close_socket(_voice_socket)
    _close_socket(_control_socket)

    _config_data = None
    _openai_client = None
    _voice_socket = None
    _control_socket = None
    _ui_language = None
    _prompt_language = None
    _general_model = None
    _translation_model = None
    _vision_model = None
    _openai_keep_alive = None
    _openai_enable_thinking = None
    _openai_thinking_budget = None
    _openai_max_output_tokens = None
    _openai_translation_max_output_tokens = None
    _openai_prompt_temperature = None
    _openai_prompt_frequency_penalty = None
    _tts_engine = None
    _tts_voice = None
    _voice_cache_dir = None
    _soul_language = None
    _soul_content = None

    init()


def get_soul_content():
    """Singleton to read and cache SOUL content once."""
    global _soul_content

    if _soul_content is None:
        soul_path = os.path.join(CONFIG_DIR, f'SOUL.{get_ui_language()}.md')
        fallback_path = os.path.join(CONFIG_DIR, 'SOUL.en.md')

        # First try to load SOUL content in UI language,
        # if not found, fallback to English version
        try:
            with open(soul_path, 'r', encoding='utf-8') as f:
                _soul_content = f.read().strip()
                print(f'Loaded SOUL content from {soul_path}')
        except FileNotFoundError:
            with open(fallback_path, 'r', encoding='utf-8') as f:
                _soul_content = f.read().strip()
                print(f'Loaded SOUL content from {fallback_path}')

            # If the fallback was used, and prompt is not in English,
            # try to translate it to ui language
            if get_prompt_language() != 'en' and get_ui_language() != 'en':
                import utils

                print(f'Translating SOUL content to {get_ui_language()}...')
                _soul_content = utils.translate(_soul_content, 'en', get_ui_language())

    return _soul_content


def get_ui_language():
    """Singleton to ensure UI language stays in memory."""
    global _ui_language

    if _ui_language is None:
        language = str(_get_config_value('language', 'ui', DEFAULT_UI_LANG))
        _ui_language = _normalize_lang(language, DEFAULT_UI_LANG)
        print(f'Using UI language: {_ui_language}')

    return _ui_language


def get_prompt_language():
    """Singleton to ensure prompt language stays in memory."""
    global _prompt_language

    if _prompt_language is None:
        prompt_language = _get_config_value('language', 'prompt', DEFAULT_PROMPT_LANG)
        _prompt_language = _normalize_lang(prompt_language, DEFAULT_PROMPT_LANG)
        print(f'Using prompt language: {_prompt_language}')

    return _prompt_language


def needs_translation():
    """Check if translation is needed based on UI language."""
    need1 = get_ui_language() is not None
    need2 = get_ui_language() != get_prompt_language()
    return need1 and need2


def get_general_model():
    """Singleton to ensure general model stays in memory."""
    global _general_model

    if _general_model is None:
        _general_model = _get_config_value('models', 'general', DEFAULT_MODEL)
        print(f'Using general model: {_general_model}')

        # Warm-load the selected model through OpenAI-compatible API once.
        # This is best-effort and should not block startup on transient backend issues.
        try:
            client = get_openai_client()
            client.chat.completions.create(
                model=_general_model,
                messages=[{'role': 'user', 'content': 'ping'}],
                max_tokens=1,
                temperature=0,
                extra_body=get_openai_general_extra_body(num_predict=1),
            )
            print(f'General model warm-loaded with keep_alive={get_openai_keep_alive()}')
        except Exception as exc:
            print(f'Warning: unable to warm-load general model {_general_model}: {exc}')

    return _general_model


def get_openai_keep_alive():
    """Singleton to ensure OpenAI-compatible keep_alive stays in memory."""
    global _openai_keep_alive

    if _openai_keep_alive is None:
        keep_alive = _get_config_value('openai', 'keep_alive', DEFAULT_OPENAI_KEEP_ALIVE)
        _openai_keep_alive = str(keep_alive or DEFAULT_OPENAI_KEEP_ALIVE).strip()
        print(f'Using OpenAI keep_alive: {_openai_keep_alive}')

    return _openai_keep_alive


def get_openai_enable_thinking():
    """Singleton to ensure OpenAI-compatible enable_thinking stays in memory."""
    global _openai_enable_thinking

    if _openai_enable_thinking is None:
        raw_value = _get_config_value('openai', 'enable_thinking', DEFAULT_OPENAI_ENABLE_THINKING)
        if isinstance(raw_value, bool):
            _openai_enable_thinking = raw_value
        elif isinstance(raw_value, str):
            _openai_enable_thinking = raw_value.strip().lower() in ('1', 'true', 'yes', 'on')
        else:
            _openai_enable_thinking = bool(raw_value)

        print(f'Using OpenAI enable_thinking: {_openai_enable_thinking}')

    return _openai_enable_thinking


def get_openai_thinking_budget():
    """Singleton to ensure OpenAI-compatible thinking_budget stays in memory."""
    global _openai_thinking_budget

    if _openai_thinking_budget is None:
        raw_value = _get_config_value('openai', 'thinking_budget', DEFAULT_OPENAI_THINKING_BUDGET)
        try:
            _openai_thinking_budget = max(0, int(raw_value))
        except (TypeError, ValueError):
            _openai_thinking_budget = DEFAULT_OPENAI_THINKING_BUDGET

        print(f'Using OpenAI thinking_budget: {_openai_thinking_budget}')

    return _openai_thinking_budget


def get_openai_max_output_tokens():
    """Singleton to ensure max output token limit stays in memory."""
    global _openai_max_output_tokens

    if _openai_max_output_tokens is None:
        raw_value = _get_config_value('openai', 'max_output_tokens', DEFAULT_OPENAI_MAX_OUTPUT_TOKENS)
        try:
            _openai_max_output_tokens = max(1, int(raw_value))
        except (TypeError, ValueError):
            _openai_max_output_tokens = DEFAULT_OPENAI_MAX_OUTPUT_TOKENS

        print(f'Using OpenAI max_output_tokens: {_openai_max_output_tokens}')

    return _openai_max_output_tokens


def get_openai_translation_max_output_tokens():
    """Singleton to ensure translation output token limit stays in memory."""
    global _openai_translation_max_output_tokens

    if _openai_translation_max_output_tokens is None:
        raw_value = _get_config_value(
            'openai',
            'translation_max_output_tokens',
            DEFAULT_OPENAI_TRANSLATION_MAX_OUTPUT_TOKENS,
        )
        try:
            _openai_translation_max_output_tokens = max(1, int(raw_value))
        except (TypeError, ValueError):
            _openai_translation_max_output_tokens = DEFAULT_OPENAI_TRANSLATION_MAX_OUTPUT_TOKENS

        print(
            f'Using OpenAI translation_max_output_tokens: '
            f'{_openai_translation_max_output_tokens}'
        )

    return _openai_translation_max_output_tokens


def get_openai_prompt_temperature():
    """Singleton to ensure prompt temperature stays in memory."""
    global _openai_prompt_temperature

    if _openai_prompt_temperature is None:
        raw_value = _get_config_value(
            'openai',
            'prompt_temperature',
            DEFAULT_OPENAI_PROMPT_TEMPERATURE,
        )
        try:
            _openai_prompt_temperature = float(raw_value)
        except (TypeError, ValueError):
            _openai_prompt_temperature = DEFAULT_OPENAI_PROMPT_TEMPERATURE

        print(f'Using OpenAI prompt_temperature: {_openai_prompt_temperature}')

    return _openai_prompt_temperature


def get_openai_prompt_frequency_penalty():
    """Singleton to ensure prompt frequency penalty stays in memory."""
    global _openai_prompt_frequency_penalty

    if _openai_prompt_frequency_penalty is None:
        raw_value = _get_config_value(
            'openai',
            'prompt_frequency_penalty',
            DEFAULT_OPENAI_PROMPT_FREQUENCY_PENALTY,
        )
        try:
            _openai_prompt_frequency_penalty = float(raw_value)
        except (TypeError, ValueError):
            _openai_prompt_frequency_penalty = DEFAULT_OPENAI_PROMPT_FREQUENCY_PENALTY

        print(
            f'Using OpenAI prompt_frequency_penalty: '
            f'{_openai_prompt_frequency_penalty}'
        )

    return _openai_prompt_frequency_penalty


def get_openai_general_extra_body(num_predict=None):
    """Build model-specific extra_body payload for OpenAI-compatible backends."""
    thinking_enabled = get_openai_enable_thinking()
    extra_body = {
        'keep_alive': get_openai_keep_alive(),
        'enable_thinking': thinking_enabled,
        'think': thinking_enabled,
    }

    if num_predict is None:
        num_predict = get_openai_max_output_tokens()

    try:
        extra_body['num_predict'] = max(1, int(num_predict))
    except (TypeError, ValueError):
        extra_body['num_predict'] = get_openai_max_output_tokens()

    if thinking_enabled:
        extra_body['thinking_budget'] = get_openai_thinking_budget()

    return extra_body


def get_translation_model():
    """Singleton to ensure translation model stays in memory."""
    global _translation_model

    if _translation_model is None:
        translation_model = _get_config_value('models', 'translation', get_general_model())
        _translation_model = translation_model or get_general_model()
        print(f'Using translation model: {_translation_model}')

    return _translation_model


def get_vision_model():
    """Singleton to ensure vision model stays in memory."""
    global _vision_model

    if _vision_model is None:
        vision_model = _get_config_value('models', 'vision', get_general_model())
        _vision_model = vision_model or get_general_model()
        print(f'Using vision model: {_vision_model}')

    return _vision_model


def get_openai_client():
    """Singleton to ensure openai client stays in memory."""
    global _openai_client

    if _openai_client is None:
        api_base = _get_config_value('openai', 'api_base')
        api_key = _get_config_value('openai', 'api_key', DEFAULT_OPENAI_API_KEY)
        if not api_base:
            raise ValueError(f'openai.api_base is not set in {CONFIG_PATH}')
        try:
            OpenAI = importlib.import_module('openai').OpenAI
        except ModuleNotFoundError as exc:
            error_message = 'The openai package is required to initialize the OpenAI client'
            print(error_message)
            raise RuntimeError(error_message) from exc

        client = OpenAI(api_key=api_key, base_url=api_base)

        try:
            models = client.models.list()
            available_models = [model.id for model in models.data[:5]]
        except Exception as exc:
            error_message = f'OpenAI server is not available at {api_base}: {exc}'
            print(error_message)
            raise RuntimeError(error_message) from exc

        _openai_client = client
        print(f'Initialized OpenAI client with base URL: {api_base}')
        print(f'Available OpenAI models: {available_models}')

    return _openai_client


def get_tts_engine_and_voice():
    """Singleton to ensure TTS settings stay in memory."""
    global _tts_engine
    global _tts_voice

    if _tts_engine is None or _tts_voice is None:
        _tts_engine = _get_config_value('tts', 'engine_api', '')
        _tts_voice = _get_config_value('tts', 'voice', '')
        print(f'Using TTS engine: {_tts_engine} with voice: {_tts_voice}')

    return _tts_engine, _tts_voice


def get_voice_cache_dir():
    """Singleton to ensure the voice cache directory exists and stays in memory."""
    global _voice_cache_dir

    if _voice_cache_dir is None:
        cache_dir = _get_config_value('tts', 'cache_dir', DEFAULT_VOICE_CACHE_DIR)
        _voice_cache_dir = os.path.expanduser(str(cache_dir or DEFAULT_VOICE_CACHE_DIR))
        os.makedirs(_voice_cache_dir, exist_ok=True)
        print(f'Using voice cache directory: {_voice_cache_dir}')

    return _voice_cache_dir


def get_voice_socket():
    """Singleton to ensure voice socket stays in memory."""
    global _voice_socket

    if _voice_socket is None:
        voice_port = int(_get_config_value('ports', 'voice', DEFAULT_VOICE_PORT))
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(('localhost', voice_port))
        _voice_socket = sock

    return _voice_socket


def get_control_socket():
    """Singleton to ensure control socket stays in memory."""
    global _control_socket

    if _control_socket is None:
        control_port = int(_get_config_value('ports', 'control', DEFAULT_CONTROL_PORT))
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(('localhost', control_port))
        _control_socket = sock

    return _control_socket
