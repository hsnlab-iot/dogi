import os
import socket
import importlib
from pathlib import Path
from boltons.fileutils import atomic_save
try:
    tomllib = importlib.import_module('tomllib')
except ModuleNotFoundError:
    tomllib = importlib.import_module('tomli')


SRC_DIR = os.path.dirname(os.path.abspath(__file__))
CONTROL_DIR = os.path.dirname(SRC_DIR)
CONFIG_DIR = os.path.join(CONTROL_DIR, 'config')

def _build_runtime_state():
    return {
        'folder': None,
        'config_data': None,
        'prompts_data': None,
        'openai_client': None,
        'voice_port': None,
        'control_socket': None,
        'ui_language': None,
        'prompt_language': None,
        'general_model': None,
        'translation_model': None,
        'vision_model': None,
        'openai_keep_alive': None,
        'openai_enable_thinking': None,
        'openai_thinking_budget': None,
        'openai_max_output_tokens': None,
        'openai_translation_max_output_tokens': None,
        'openai_prompt_temperature': None,
        'openai_prompt_frequency_penalty': None,
        'openai_binary_images': None,
        'tts_api_base': None,
        'tts_voice': None,
        'tts_model': None,
        'tts_protocol': None,
        'cache_dir': None,
        'soul_content': None,
        'tools_list': None,
        'log_dir': None,
    }


_state = _build_runtime_state()

def _build_default_config():
    return {
        'general': {
            'cache_dir': '~/.cache/',
        },
        'language': {
            'ui': 'en',
            'prompt': 'en',
        },
        'models': {
            'general': 'qwen3.5:4b',
            'vision': '',
            'translation': 'opus',
        },
        'openai': {
            'api_base': 'http://localhost:11434/v1',
            'api_key': 'not-needed',
            'keep_alive': '30m',
            'enable_thinking': False,
            'thinking_budget': 500,
            'max_output_tokens': 512,
            'translation_max_output_tokens': 1024,
            'prompt_temperature': 0.3,
            'prompt_frequency_penalty': 1.5,
            'binary_images': False,
        },
        'tts': {
            'api_base': '',
            'voice': '',
            'model': '',
            'protocol': 'mms',  # 'opentts' | 'openai' | 'mms'
        },
        'ports': {
            'voice': 5059,
            'control': 5002,
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
    config_dir = Path(CONFIG_DIR)
    config_path = (
        config_dir / _state['folder'] / 'config.toml' if _state['folder']
        else config_dir / 'config.toml'
    )
    
    if not config_path.exists():
        print(f'Warning: config file does not exist: {config_path}. Using defaults.')
        return defaults

    loaded = tomllib.loads(config_path.read_text(encoding="utf-8"))

    if not isinstance(loaded, dict):
        print(f'Warning: config file has invalid structure: {config_path}')
        return defaults

    print(f"Config file loaded: {config_path}")
    return _merge_dict(defaults, loaded)


def _load_prompts_file():
    config_dir = Path(CONFIG_DIR)
    prompts_path = (
        config_dir / _state['folder'] / 'prompts.toml' if _state['folder']
        else config_dir / 'prompts.toml'
    )

    if not prompts_path.exists():
        print(f'Warning: prompts file does not exist: {prompts_path}')
        return {}

    loaded = tomllib.loads(prompts_path.read_text(encoding="utf-8"))

    if not isinstance(loaded, dict):
        print(f'Warning: prompts file has invalid structure: {prompts_path}')
        return {}

    print(f"Prompts file loaded: {prompts_path}")
    return loaded


def get_config_data():
    if _state['folder'] is None:
        init()

    print(f"get_config_data with folder: '{_state['folder']}'")

    if _state['config_data'] is None:
        _state['config_data'] = _load_config_file()

    return _state['config_data']


def get_prompts_data():
    if _state['prompts_data'] is None:
        _state['prompts_data'] = _load_prompts_file()

    return _state['prompts_data']


def _format_prompt_entry(prompt_entry, format_kwargs):
    if not format_kwargs:
        return prompt_entry

    if isinstance(prompt_entry, str):
        return prompt_entry.format(**format_kwargs)

    if isinstance(prompt_entry, dict):
        formatted = {}
        for key, value in prompt_entry.items():
            if isinstance(value, str):
                formatted[key] = value.format(**format_kwargs)
            else:
                formatted[key] = value
        return formatted

    return prompt_entry


def get_prompt(section, key, **format_kwargs):
    section_data = get_prompts_data().get(section)
    if not isinstance(section_data, dict):
        raise KeyError(f'Prompt section not found: {section}')

    if key not in section_data:
        raise KeyError(f'Prompt key not found: {section}.{key}')

    prompt_entry = section_data[key]
    if not isinstance(prompt_entry, (str, dict)):
        raise TypeError(
            f'Prompt entry must be string or language map for {section}.{key}, '
            f'got {type(prompt_entry).__name__}'
        )

    return _format_prompt_entry(prompt_entry, format_kwargs)


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


def init(folder = ''):
    """Initialize configuration by loading config and priming singletons."""
    if _state['config_data'] is not None:
        print("Config alredy initialized")
        return

    if not folder:
        # Check selected file for selection
        selected_file = os.path.join(CONFIG_DIR, 'selected')
        if os.path.exists(selected_file):
            try:
                with open(selected_file, 'r', encoding='utf-8') as f:
                    folder = f.read().strip()
                # Validate that the selected folder exists
                selected_folder_path = os.path.join(CONFIG_DIR, folder)
                if not os.path.isdir(selected_folder_path):
                    print(f'Error: selected folder does not exist: {selected_folder_path}')
                    folder = ''
                else:
                    print(f'Loaded selected folder from file: {folder}')
            except Exception as e:
                print(f'Error reading selected file: {e}')
                folder = ''
        else:
            print("There is no selected pupality")

    _state['folder'] = folder
    print(f"Initializing config with folder: '{_state['folder']}'")
    _state['config_data'] = _load_config_file()
    
    """
    # Load this on damand

    get_ui_language()
    get_prompt_language()
    get_translation_model()
    get_openai_client()
    get_soul_content()
    get_tts_parameters()
    get_control_socket()
    """

def reinit(folder = ''):
    """Reload configuration from disk and rebuild cached clients and sockets."""
    _close_socket(_state['control_socket'])

    _state.update(_build_runtime_state())
    _state['folder'] = None

    if (folder):
        print(f"Reinit with {folder}")
    else:
        print("Reinit")
   
    # Save selected folder to file using bolton for atomic writes
    selected_file = os.path.join(CONFIG_DIR, 'selected')
    try:
        with atomic_save(selected_file, text_mode=True) as f:
            f.write(folder)
        print(f"Saved selected folder to {selected_file}: '{folder}'")
    except Exception as e:
        print(f'Error saving selected folder: {e}')

    init(folder)


def get_soul_content():
    """Singleton to read and cache SOUL content once."""
    if _state['soul_content'] is None:

        fallback = False
        config_dir = Path(CONFIG_DIR)
        soul_filename = f'SOUL.{get_prompt_language()}.md'
        soul_path = (
            config_dir / _state['folder'] / soul_filename if _state['folder']
            else config_dir / soul_filename
        )
    
        if not soul_path.exists():
            soul_filename = 'SOUL.en.md'
            soul_path = (
                config_dir / _state['folder'] / soul_filename if _state['folder']
                else config_dir / soul_filename
            )
            fallback = True

        try:
            _state['soul_content'] = soul_path.read_text(encoding='utf-8').strip()
            print(f'Loaded SOUL content from {soul_path}')
        except Exception as e:
            _state['soul_content'] = ''
            print(f"Load error: {e}")
        
        # If the fallback was used, and prompt is not in English,
        # try to translate it to ui language
        if fallback or get_prompt_language() != 'en':
            import utils

            print(f'Translating SOUL content to {get_prompt_language()}...')
            _state['soul_content'] = utils.translate(
                _state['soul_content'],
                'en',
                get_prompt_language(),
            )

    return _state['soul_content']


# When prompt and ui languages are different then translation is needed,
# but if prompt language is not set, we assume it's the same as
# ui language and skip translation.

def get_ui_language():
    """Singleton to ensure UI language stays in memory."""
    if _state['ui_language'] is None:
        language = str(_get_config_value('language', 'ui'))
        _state['ui_language'] = _normalize_lang(language, 'en')
        print(f"Using UI language: {_state['ui_language']}")

    return _state['ui_language']


def get_prompt_language():
    """Singleton to ensure prompt language stays in memory."""
    if _state['prompt_language'] is None:
        prompt_language = _get_config_value('language', 'prompt')
        _state['prompt_language'] = _normalize_lang(prompt_language, 'en')
        print(f"Using prompt language: {_state['prompt_language']}")

    return _state['prompt_language']


def needs_translation():
    """Check if translation is needed based on UI language."""
    need1 = get_ui_language() is not None
    need2 = get_ui_language() != get_prompt_language()
    return need1 and need2


def get_general_model():
    """Singleton to ensure general model stays in memory."""
    if _state['general_model'] is None:
        _state['general_model'] = _get_config_value('models', 'general')
        print(f"Using general model: {_state['general_model']}")

        # Warm-load the selected model through OpenAI-compatible API once.
        # This is best-effort and should not block startup on transient backend issues.
        try:
            client = get_openai_client()
            client.chat.completions.create(
                model=_state['general_model'],
                messages=[{'role': 'user', 'content': 'ping'}],
                max_tokens=1,
                temperature=0,
                extra_body=get_openai_general_extra_body(num_predict=1),
            )
            print(f'General model warm-loaded with keep_alive={get_openai_keep_alive()}')
        except Exception as exc:
            print(f"Warning: unable to warm-load general model {_state['general_model']}: {exc}")

    return _state['general_model']


def get_openai_keep_alive():
    """Singleton to ensure OpenAI-compatible keep_alive stays in memory."""
    if _state['openai_keep_alive'] is None:
        keep_alive = _get_config_value('openai', 'keep_alive', '30m')
        _state['openai_keep_alive'] = str(keep_alive or '30m').strip()
        print(f"Using OpenAI keep_alive: {_state['openai_keep_alive']}")

    return _state['openai_keep_alive']


def get_openai_enable_thinking():
    """Singleton to ensure OpenAI-compatible enable_thinking stays in memory."""
    if _state['openai_enable_thinking'] is None:
        raw_value = _get_config_value('openai', 'enable_thinking')
        if isinstance(raw_value, bool):
            _state['openai_enable_thinking'] = raw_value
        elif isinstance(raw_value, str):
            _state['openai_enable_thinking'] = raw_value.strip().lower() in ('1', 'true', 'yes', 'on')
        else:
            _state['openai_enable_thinking'] = bool(raw_value)

        print(f"Using OpenAI enable_thinking: {_state['openai_enable_thinking']}")

    return _state['openai_enable_thinking']


def get_openai_thinking_budget():
    """Singleton to ensure OpenAI-compatible thinking_budget stays in memory."""
    if _state['openai_thinking_budget'] is None:
        raw_value = _get_config_value('openai', 'thinking_budget')
        try:
            _state['openai_thinking_budget'] = max(0, int(raw_value))
        except (TypeError, ValueError):
            _state['openai_thinking_budget'] = 500

        print(f"Using OpenAI thinking_budget: {_state['openai_thinking_budget']}")

    return _state['openai_thinking_budget']


def get_openai_max_output_tokens():
    """Singleton to ensure max output token limit stays in memory."""
    if _state['openai_max_output_tokens'] is None:
        raw_value = _get_config_value('openai', 'max_output_tokens')
        try:
            _state['openai_max_output_tokens'] = max(1, int(raw_value))
        except (TypeError, ValueError):
            _state['openai_max_output_tokens'] = 512

        print(f"Using OpenAI max_output_tokens: {_state['openai_max_output_tokens']}")

    return _state['openai_max_output_tokens']


def get_openai_translation_max_output_tokens():
    """Singleton to ensure translation output token limit stays in memory."""
    if _state['openai_translation_max_output_tokens'] is None:
        raw_value = _get_config_value(
            'openai',
            'translation_max_output_tokens'
        )
        try:
            _state['openai_translation_max_output_tokens'] = max(1, int(raw_value))
        except (TypeError, ValueError):
            _state['openai_translation_max_output_tokens'] = 1024

        print(
            f'Using OpenAI translation_max_output_tokens: '
            f"{_state['openai_translation_max_output_tokens']}"
        )

    return _state['openai_translation_max_output_tokens']


def get_openai_prompt_temperature():
    """Singleton to ensure prompt temperature stays in memory."""
    if _state['openai_prompt_temperature'] is None:
        raw_value = _get_config_value(
            'openai',
            'prompt_temperature'
        )
        try:
            _state['openai_prompt_temperature'] = float(raw_value)
        except (TypeError, ValueError):
            _state['openai_prompt_temperature'] = 0.3

        print(f"Using OpenAI prompt_temperature: {_state['openai_prompt_temperature']}")

    return _state['openai_prompt_temperature']


def get_openai_prompt_frequency_penalty():
    """Singleton to ensure prompt frequency penalty stays in memory."""
    if _state['openai_prompt_frequency_penalty'] is None:
        raw_value = _get_config_value(
            'openai',
            'prompt_frequency_penalty'
        )
        try:
            _state['openai_prompt_frequency_penalty'] = float(raw_value)
        except (TypeError, ValueError):
            _state['openai_prompt_frequency_penalty'] = 1.5

        print(
            f'Using OpenAI prompt_frequency_penalty: '
            f"{_state['openai_prompt_frequency_penalty']}"
        )

    return _state['openai_prompt_frequency_penalty']


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


def get_openai_binary_images():
    """Singleton to ensure OpenAI-compatible binary image setting stays in memory."""
    if _state['openai_binary_images'] is None:
        raw_value = _get_config_value(
            'openai',
            'binary_images',
            )
        if isinstance(raw_value, bool):
            _state['openai_binary_images'] = raw_value
        elif isinstance(raw_value, str):
            _state['openai_binary_images'] = raw_value.strip().lower() in ('1', 'true', 'yes', 'on')
        else:
            _state['openai_binary_images'] = bool(raw_value)

        print(f"Using OpenAI binary_images: {_state['openai_binary_images']}")

    return _state['openai_binary_images']

def get_translation_model():
    """Singleton to ensure translation model stays in memory."""
    if _state['translation_model'] is None:
        translation_model = _get_config_value('models', 'translation', get_general_model())
        _state['translation_model'] = translation_model or get_general_model()
        print(f"Using translation model: {_state['translation_model']}")

    return _state['translation_model']


def get_vision_model():
    """Singleton to ensure vision model stays in memory."""
    if _state['vision_model'] is None:
        vision_model = _get_config_value('models', 'vision', get_general_model())
        _state['vision_model'] = vision_model or get_general_model()
        print(f"Using vision model: {_state['vision_model']}")

    return _state['vision_model']


def get_openai_client():
    """Singleton to ensure openai client stays in memory."""
    if _state['openai_client'] is None:
        api_base = _get_config_value('openai', 'api_base')
        api_key = _get_config_value('openai', 'api_key')
        if not api_base:
            raise ValueError(f'openai.api_base is not set in {CONFIG_PATH}')
        try:
            from phoenix.otel import register
            tracer_provider = register(
                project_name="dogi-llm-agent-debugging",
                auto_instrument=True # Automatically hooks into installed OpenInference packages
            )
        except ModuleNotFoundError as exc:
            error_message = 'The phoenix.otel package is required to debug the OpenAI client'
            print(error_message)
            pass

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

        _state['openai_client'] = client
        print(f'Initialized OpenAI client with base URL: {api_base}')
        print(f'Available OpenAI models: {available_models}')

    return _state['openai_client']


def get_tts_parameters():
    """Singleton to ensure TTS settings stay in memory.

    Returns:
        (api_base, voice, model, protocol) where protocol is one of:
        'opentts' – OpenTTS HTTP server (uses voice)
        'openai'  – OpenAI-compatible TTS API (uses model + voice)
        'mms'     – MMS built-in TTS engine (uses model)
    """
    if (
        _state['tts_api_base'] is None
        or _state['tts_voice'] is None
        or _state['tts_model'] is None
        or _state['tts_protocol'] is None
    ):
        _state['tts_api_base'] = _get_config_value('tts', 'api_base')
        _state['tts_voice'] = _get_config_value('tts', 'voice')
        _state['tts_model'] = _get_config_value('tts', 'model')
        _state['tts_protocol'] = str(
            _get_config_value('tts', 'protocol') or 'mms'
        ).strip().lower()

        if _state['tts_protocol'] == 'openai':
            # Accept either a full speech endpoint or a generic OpenAI-compatible base URL.
            if _state['tts_api_base'].endswith('/audio/speech'):
                # remove ending
                _state['tts_api_base'] = _state['tts_api_base'][:-len('/audio/speech')]
        print(
            f"Using TTS protocol: {_state['tts_protocol']}, api_base: {_state['tts_api_base']}, "
            f"voice: {_state['tts_voice']}, model: {_state['tts_model']}"
        )

    return (
        _state['tts_api_base'],
        _state['tts_voice'],
        _state['tts_model'],
        _state['tts_protocol'],
    )


def get_cache_dir():
    """Singleton to ensure the voice cache directory exists and stays in memory."""
    if _state['cache_dir'] is None:
        cache_dir = _get_config_value('general', 'cache_dir')
        _state['cache_dir'] = os.path.expanduser(str(cache_dir or '~/.cache/'))
        os.makedirs(_state['cache_dir'], exist_ok=True)
        print(f"Using cache directory: {_state['cache_dir']}")

    return _state['cache_dir']


def get_log_dir():
    """Return configured log directory from [general].log or None if not set.

    If present, expands `~` and ensures the directory exists (like get_cache_dir).
    """
    if _state['log_dir'] is None:
        log_dir = _get_config_value('general', 'log')
        if not log_dir:
            _state['log_dir'] = None
        else:
            _state['log_dir'] = os.path.expanduser(str(log_dir))
            try:
                os.makedirs(_state['log_dir'], exist_ok=True)
            except Exception:
                # If directory creation fails, still return the expanded path
                pass
            print(f"Using log directory: {_state['log_dir']}")

    return _state['log_dir']


def get_voice_port():
    """Singleton to ensure voice port stays in memory."""
    if _state['voice_port'] is None:
        _state['voice_port'] = int(_get_config_value('ports', 'voice'))
    return _state['voice_port']


def get_control_socket():
    """Singleton to ensure control socket stays in memory."""
    if _state['control_socket'] is None:
        control_port = int(_get_config_value('ports', 'control'))
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(('localhost', control_port))
        _state['control_socket'] = sock

    return _state['control_socket']

def get_tools():
    """Singleton to read and cache tools config once."""
    if _state['tools_list'] is None:
        tools_section = get_config_data().get('tools', {})

        values = []
        # If tools section is a mapping, extract its values;
        if isinstance(tools_section, dict):
            iterable = tools_section.values()
        else:
            iterable = []

        for v in iterable:
            values.append(str(v))

        _state['tools_list'] = values

    return _state['tools_list']