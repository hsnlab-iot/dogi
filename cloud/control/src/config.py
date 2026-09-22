import os
import json
import socket
import importlib
import re
from pathlib import Path
from boltons.fileutils import atomic_save
import ollama as ollama_runtime
try:
    tomllib = importlib.import_module('tomllib')
except ModuleNotFoundError:
    tomllib = importlib.import_module('tomli')


SRC_DIR = os.path.dirname(os.path.abspath(__file__))
CONTROL_DIR = os.path.dirname(SRC_DIR)
CONFIG_DIR = os.path.join(CONTROL_DIR, 'config')
AGENTS_DIR = os.path.join(CONFIG_DIR, 'agents')
TOOLS_DIR = os.path.join(CONFIG_DIR, 'tools')
SKILLS_DIR = os.path.join(CONFIG_DIR, 'skills')


def _resolve_agent_dir(folder_name):
    """Resolve selected agent directory with fallback for legacy layout."""
    if not folder_name:
        return None

    preferred = Path(AGENTS_DIR) / folder_name
    if preferred.is_dir():
        return preferred

    legacy = Path(CONFIG_DIR) / folder_name
    if legacy.is_dir():
        return legacy

    return None


def _get_current_agent_dir():
    return _resolve_agent_dir(_state['folder'])


def _load_structured_file(path):
    suffix = path.suffix.lower()
    if suffix == '.json':
        return json.loads(path.read_text(encoding='utf-8'))
    if suffix == '.toml':
        return tomllib.loads(path.read_text(encoding='utf-8'))
    if suffix in ('.yaml', '.yml'):
        try:
            yaml = importlib.import_module('yaml')
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"PyYAML is required to parse '{path.name}'"
            ) from exc
        return yaml.safe_load(path.read_text(encoding='utf-8'))

    raise ValueError(f'Unsupported descriptor file extension: {path.suffix}')


def _load_tool_descriptor_file(tool_ref):
    if not tool_ref:
        return None, None

    tools_dir = Path(TOOLS_DIR)
    direct_path = tools_dir / tool_ref

    candidates = []
    if direct_path.suffix:
        candidates.append(direct_path)
    else:
        candidates.extend([
            tools_dir / f'{tool_ref}.yaml',
            tools_dir / f'{tool_ref}.yml',
            tools_dir / f'{tool_ref}.json',
            tools_dir / f'{tool_ref}.toml',
        ])

    for candidate in candidates:
        if not candidate.exists() or not candidate.is_file():
            continue
        data = _load_structured_file(candidate)
        if not isinstance(data, dict):
            print(f'Warning: tool descriptor is not an object: {candidate}')
            return None, None
        return candidate, data

    print(f'Warning: tool descriptor not found for ref: {tool_ref}')
    return None, None


def _normalize_tool_tag(tag):
    cleaned = re.sub(r'[^a-z0-9_\-/]+', '-', str(tag).strip().lower())
    cleaned = re.sub(r'-+', '-', cleaned).strip('-')
    return cleaned


def _extract_tags_from_source_file(source_file):
    if not source_file:
        return []

    path = Path(source_file)
    if not path.exists() or not path.is_file():
        return []

    try:
        content = path.read_text(encoding='utf-8')
    except Exception as exc:
        print(f'Warning: failed to read source file for tags {path}: {exc}')
        return []

    raw_tags = set()
    for match in re.findall(r'def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', content):
        raw_tags.add(match)
    for match in re.findall(r'name\s*=\s*[\"\']([^\"\']+)[\"\']', content):
        raw_tags.add(match)
    for match in re.findall(r'description\s*=\s*[\"\']([^\"\']+)[\"\']', content):
        for token in re.split(r'[^a-zA-Z0-9_\-/]+', match):
            if len(token) >= 4:
                raw_tags.add(token)

    normalized = []
    for tag in raw_tags:
        candidate = _normalize_tool_tag(tag)
        if not candidate or len(candidate) < 3:
            continue
        normalized.append(candidate)

    return sorted(set(normalized))


def _extract_tool_ids_from_source_file(source_file, server_name):
    if not source_file:
        return []

    path = Path(source_file)
    if not path.exists() or not path.is_file():
        return []

    try:
        content = path.read_text(encoding='utf-8')
    except Exception:
        return []

    tool_names = set()

    for match in re.findall(r'name\s*=\s*[\"\']([^\"\']+)[\"\']', content):
        if match:
            tool_names.add(match.strip())

    for match in re.findall(r'@mcp\.tool\(\)\s*\ndef\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', content):
        if match:
            tool_names.add(match.strip())

    ids = []
    for tool_name in sorted(tool_names):
        ids.append(f'{server_name}/{tool_name}')

    return ids


def _tool_descriptor_to_endpoint(tool_ref, descriptor_file, descriptor):
    kind = str(descriptor.get('type') or '').strip().lower()
    target = descriptor.get('url') or descriptor.get('target') or descriptor.get('connection')
    target = str(target or '').strip()

    if not kind or not target:
        print(
            f'Warning: invalid tool descriptor in {descriptor_file}. '
            f"Expected 'type' and 'url/target/connection'."
        )
        return None, None

    endpoint = f'{kind}!{target}'
    source_file = str(descriptor.get('source_file') or '').strip()
    if source_file and not Path(source_file).is_absolute():
        source_file = str((Path(CONTROL_DIR) / source_file).resolve())

    raw_tags = descriptor.get('tags')
    tags = []
    if isinstance(raw_tags, list):
        tags = [_normalize_tool_tag(tag) for tag in raw_tags if _normalize_tool_tag(tag)]
    if not tags:
        tags = _extract_tags_from_source_file(source_file)

    provided_tools = descriptor.get('provided_mcp_tools')
    if isinstance(provided_tools, list):
        provided_mcp_tools = [str(v).strip() for v in provided_tools if str(v).strip()]
    else:
        provided_mcp_tools = []

    server_name = str(descriptor.get('name') or Path(str(tool_ref)).stem)
    if not provided_mcp_tools:
        provided_mcp_tools = _extract_tool_ids_from_source_file(source_file, server_name)

    metadata = {
        'ref': str(tool_ref),
        'file': str(descriptor_file),
        'name': server_name,
        'description': str(descriptor.get('description') or ''),
        'type': kind,
        'url': target,
        'endpoint': endpoint,
        'tags': tags,
        'source_file': source_file,
        'provided_mcp_tools': provided_mcp_tools,
    }

    return endpoint, metadata


def _parse_markdown_frontmatter(content):
    stripped = content.strip()
    if not stripped.startswith('---\n'):
        return {}, content.strip()

    closing_idx = stripped.find('\n---\n', 4)
    if closing_idx < 0:
        return {}, content.strip()

    header = stripped[4:closing_idx]
    body = stripped[closing_idx + 5:].strip()

    try:
        yaml = importlib.import_module('yaml')
        metadata = yaml.safe_load(header)
        if not isinstance(metadata, dict):
            metadata = {}
    except Exception as exc:
        print(f'Warning: failed to parse skill frontmatter: {exc}')
        metadata = {}

    return metadata, body


def _load_skill_file(skill_ref):
    if not skill_ref:
        return None

    skills_dir = Path(SKILLS_DIR)
    direct_path = skills_dir / skill_ref
    candidates = []

    if direct_path.suffix:
        candidates.append(direct_path)
    else:
        candidates.extend([
            skills_dir / f'{skill_ref}.md',
            skills_dir / f'{skill_ref}.markdown',
        ])

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    return None


def _collect_available_tool_capabilities(tool_metadata):
    capabilities = set()

    for meta in tool_metadata:
        name = str(meta.get('name') or '').strip()
        if name:
            capabilities.add(name)

        for tag in meta.get('tags', []) or []:
            tag_value = _normalize_tool_tag(tag)
            if tag_value:
                capabilities.add(tag_value)

        for provided in meta.get('provided_mcp_tools', []) or []:
            provided_value = str(provided).strip()
            if provided_value:
                capabilities.add(provided_value)

    return capabilities

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
        'openai_json_scheme': None,
        'openai_binary_images': None,
        'openai_ollama': None,
        'tts_api_base': None,
        'tts_voice': None,
        'tts_model': None,
        'tts_protocol': None,
        'tts_parameters': None,
        'cache_dir': None,
        'soul_content': None,
        'tools_list': None,
        'tools_meta': None,
        'skills_list': None,
        'skills_unavailable': None,
        'skills_content': None,
        'system_prompt': None,
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
            'ollama': False,
            'keep_alive': '30m',
            'enable_thinking': False,
            'thinking_budget': 500,
            'max_output_tokens': 512,
            'translation_max_output_tokens': 1024,
            'prompt_temperature': 0.3,
            'prompt_frequency_penalty': 1.5,
            'scheme': '',
            'binary_images': False,
        },
        'tts': {
            'api_base': '',
            'voice': '',
            'model': '',
            'reference_text': '',
            'reference_wav': '',
            'repo_id': '',
            'protocol': 'mms',  # 'opentts' | 'openai' | 'mms' | 'f5'
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


def _find_f5_repo_files(snapshot_dir):
    root = Path(snapshot_dir)
    if not root.exists():
        return '', ''

    ckpt_extensions = ('.safetensors', '.ckpt', '.pt', '.pth', '.bin')
    vocab_priority_names = ('vocab.txt', 'vocab.json', 'vocabulary.txt', 'vocabulary.json')
    vocab_extensions = ('.txt', '.json', '.model')

    ckpt_file = ''
    vocab_file = ''

    for candidate in root.rglob('*'):
        if not candidate.is_file():
            continue
        lower_name = candidate.name.lower()

        if not ckpt_file and lower_name.endswith(ckpt_extensions):
            ckpt_file = str(candidate)

        if not vocab_file and lower_name in vocab_priority_names:
            vocab_file = str(candidate)

    if not vocab_file:
        for candidate in root.rglob('*'):
            if not candidate.is_file():
                continue
            lower_name = candidate.name.lower()
            if 'vocab' in lower_name and lower_name.endswith(vocab_extensions):
                vocab_file = str(candidate)
                break

    return ckpt_file, vocab_file


def _download_f5_repo_files(repo_id):
    try:
        huggingface_hub = importlib.import_module('huggingface_hub')
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "huggingface_hub package is required when [tts].repo_id is configured"
        ) from exc

    print(f"Downloading F5 model files from Hugging Face repo: {repo_id}")
    snapshot_dir = huggingface_hub.snapshot_download(repo_id=repo_id)
    ckpt_file, vocab_file = _find_f5_repo_files(snapshot_dir)

    if not ckpt_file or not vocab_file:
        raise RuntimeError(
            f"Could not detect ckpt/vocab files in Hugging Face repo '{repo_id}'. "
            f"Detected ckpt_file={ckpt_file!r}, vocab_file={vocab_file!r}."
        )

    return ckpt_file, vocab_file


def _load_config_file():
    defaults = _build_default_config()    
    config_dir = Path(CONFIG_DIR)
    agent_dir = _get_current_agent_dir()
    config_path = agent_dir / 'config.toml' if agent_dir else config_dir / 'config.toml'
    
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
    agent_dir = _get_current_agent_dir()
    prompts_path = agent_dir / 'prompts.toml' if agent_dir else config_dir / 'prompts.toml'

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
                selected_folder_path = _resolve_agent_dir(folder)
                if selected_folder_path is None:
                    print(f'Error: selected folder does not exist in {AGENTS_DIR}: {folder}')
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
    _sync_ollama_runtime_for_current_selection()
    
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

def reinit(folder = None):
    """Reload configuration from disk and rebuild cached clients and sockets."""
    previous_owner = _get_ollama_owner_id(_state.get('folder'))
    ollama_runtime.unregister_owner(previous_owner)

    _close_socket(_state['control_socket'])

    _state.update(_build_runtime_state())
    _state['folder'] = None

    if isinstance(folder, str):
        print(f"Reinit with {folder}")

        # Save selected folder to file using bolton for atomic writes
        selected_file = os.path.join(CONFIG_DIR, 'selected')
        try:
            with atomic_save(selected_file, text_mode=True) as f:
                f.write(folder)
            print(f"Saved selected folder to {selected_file}: '{folder}'")
        except Exception as e:
            print(f'Error saving selected folder: {e}')

    else:
        print("Reinit")
   
    init(folder)


def _get_ollama_owner_id(folder):
    normalized = str(folder or '').strip() or 'default'
    return f'pupality:{normalized}'


def _get_ollama_desired_models():
    models_section = get_config_data().get('models', {})
    if not isinstance(models_section, dict):
        return []

    desired = set()
    for key in ('general', 'translation', 'vision'):
        model_name = str(models_section.get(key) or '').strip()
        if not model_name:
            continue
        if model_name.lower() == 'opus':
            continue
        desired.add(model_name)

    return sorted(desired)


def _sync_ollama_runtime_for_current_selection():
    owner = _get_ollama_owner_id(_state.get('folder'))
    if not get_openai_ollama():
        ollama_runtime.unregister_owner(owner)
        return

    openai_api_base = str(_get_config_value('openai', 'api_base') or '').strip()
    if not openai_api_base:
        ollama_runtime.unregister_owner(owner)
        return

    ollama_runtime.update_owner_models(
        openai_api_base=openai_api_base,
        owner=owner,
        models=_get_ollama_desired_models(),
        keep_alive=get_openai_keep_alive(),
    )


def get_soul_content():
    """Singleton to read and cache SOUL content once."""
    if _state['soul_content'] is None:

        fallback = False
        config_dir = Path(CONFIG_DIR)
        agent_dir = _get_current_agent_dir()
        soul_filename = f'SOUL.{get_prompt_language()}.md'
        soul_path = agent_dir / soul_filename if agent_dir else config_dir / soul_filename
    
        if not soul_path.exists():
            soul_filename = 'SOUL.en.md'
            soul_path = agent_dir / soul_filename if agent_dir else config_dir / soul_filename
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


def get_openai_json_scheme():
    """Singleton to ensure OpenAI-compatible JSON scheme stays in memory."""
    if _state['openai_json_scheme'] is None:
        raw_value = _get_config_value('openai', 'scheme', '')
        _state['openai_json_scheme'] = str(raw_value or '').strip()
        print(f"Using OpenAI scheme: {_state['openai_json_scheme']}")

    return _state['openai_json_scheme']


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


def get_openai_ollama():
    """Singleton to ensure OpenAI-compatible ollama backend flag stays in memory."""
    if _state['openai_ollama'] is None:
        raw_value = _get_config_value('openai', 'ollama', False)
        if isinstance(raw_value, bool):
            _state['openai_ollama'] = raw_value
        elif isinstance(raw_value, str):
            _state['openai_ollama'] = raw_value.strip().lower() in ('1', 'true', 'yes', 'on')
        else:
            _state['openai_ollama'] = bool(raw_value)

        print(f"Using OpenAI ollama backend: {_state['openai_ollama']}")

    return _state['openai_ollama']

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
        openai -> {'api_base', 'voice', 'model'}
        f5     -> {'reference_text', 'reference_wav', 'repo_id', 'ckpt_file', 'vocab_file'}
        other  -> None
    """
    if _state['tts_parameters'] is None:
        tts_api_base = str(_get_config_value('tts', 'api_base') or '').strip()
        tts_voice = str(_get_config_value('tts', 'voice') or '').strip()
        tts_model = str(_get_config_value('tts', 'model') or '').strip()
        tts_protocol = str(_get_config_value('tts', 'protocol') or 'mms').strip().lower()
        tts_reference_text = str(_get_config_value('tts', 'reference_text', '') or '').strip()
        tts_reference_wav = str(_get_config_value('tts', 'reference_wav', '') or '').strip()
        tts_repo_id = str(_get_config_value('tts', 'repo_id', '') or '').strip()
        # Backward compatibility: explicit file paths are still accepted when repo_id is not set.
        tts_ckpt_file = str(_get_config_value('tts', 'ckpt_file', '') or '').strip()
        tts_vocab_file = str(_get_config_value('tts', 'vocab_file', '') or '').strip()

        def _resolve_tts_path(path_value):
            if not path_value:
                return ''
            resolved_path = Path(path_value).expanduser()
            if not resolved_path.is_absolute():
                agent_dir = _get_current_agent_dir()
                if agent_dir is not None:
                    resolved_path = agent_dir / resolved_path
                else:
                    resolved_path = Path(CONFIG_DIR) / resolved_path
            return str(resolved_path)

        tts_reference_wav = _resolve_tts_path(tts_reference_wav)
        if tts_repo_id:
            tts_ckpt_file, tts_vocab_file = _download_f5_repo_files(tts_repo_id)
        else:
            tts_ckpt_file = _resolve_tts_path(tts_ckpt_file)
            tts_vocab_file = _resolve_tts_path(tts_vocab_file)

        if tts_protocol == 'openai' and tts_api_base.endswith('/audio/speech'):
            # Accept either a full speech endpoint or a generic OpenAI-compatible base URL.
            tts_api_base = tts_api_base[:-len('/audio/speech')]

        _state['tts_api_base'] = tts_api_base
        _state['tts_voice'] = tts_voice
        _state['tts_model'] = tts_model
        _state['tts_protocol'] = tts_protocol
 
        if tts_protocol == 'openai':
            _state['tts_parameters'] = {
                'tts_protocol': tts_protocol,
                'api_base': tts_api_base,
                'voice': tts_voice,
                'model': tts_model,
            }
        elif tts_protocol == 'f5':
            _state['tts_parameters'] = {
                'tts_protocol': tts_protocol,
                'reference_text': tts_reference_text,
                'reference_wav': tts_reference_wav,
                'repo_id': tts_repo_id,
                'ckpt_file': tts_ckpt_file,
                'vocab_file': tts_vocab_file,
            }
        elif tts_protocol == 'mms':
            _state['tts_parameters'] = {
                'tts_protocol': tts_protocol,
                'model': tts_model
            }
        else:
            _state['tts_parameters'] = {
                'tts_protocol': tts_protocol
            }

        print(
            f"Using TTS settings: protocol={tts_protocol}, api_base={tts_api_base}, "
            f"voice={tts_voice}, model={tts_model}, tts_reference_wav={tts_reference_wav}, "
            f"tts_repo_id={tts_repo_id}, "
            f"tts_ckpt_file={tts_ckpt_file}, tts_vocab_file={tts_vocab_file}, "
            f"returned={_state['tts_parameters']}"
        )

    return _state['tts_parameters']


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
        metadata = []

        tool_refs = []
        if isinstance(tools_section, dict) and isinstance(tools_section.get('list'), list):
            tool_refs = [str(v).strip() for v in tools_section.get('list', []) if str(v).strip()]
        elif isinstance(tools_section, list):
            tool_refs = [str(v).strip() for v in tools_section if str(v).strip()]

        if tool_refs:
            for tool_ref in tool_refs:
                descriptor_file, descriptor = _load_tool_descriptor_file(tool_ref)
                if descriptor_file is None or descriptor is None:
                    continue

                endpoint, meta = _tool_descriptor_to_endpoint(tool_ref, descriptor_file, descriptor)
                if not endpoint:
                    continue

                values.append(endpoint)
                metadata.append(meta)
        elif isinstance(tools_section, dict):
            # Legacy format: [tools] table entries with inline endpoint strings.
            for name, value in tools_section.items():
                if name == 'list':
                    continue
                endpoint = str(value).strip()
                if not endpoint:
                    continue
                values.append(endpoint)
                metadata.append({
                    'ref': str(name),
                    'file': '',
                    'name': str(name),
                    'description': '',
                    'type': endpoint.split('!', 1)[0] if '!' in endpoint else '',
                    'url': endpoint.split('!', 1)[1] if '!' in endpoint else endpoint,
                    'endpoint': endpoint,
                    'tags': [],
                    'source_file': '',
                    'provided_mcp_tools': [],
                })

        _state['tools_list'] = values
        _state['tools_meta'] = metadata

    return _state['tools_list']


def get_tools_metadata():
    if _state['tools_meta'] is None:
        get_tools()
    return _state['tools_meta'] or []


def get_skills():
    """Return selected runtime skill file refs from config.toml."""
    if _state['skills_list'] is None:
        skills_section = get_config_data().get('skills', {})
        values = []

        if isinstance(skills_section, dict) and isinstance(skills_section.get('list'), list):
            values = [str(v).strip() for v in skills_section.get('list', []) if str(v).strip()]
        elif isinstance(skills_section, list):
            values = [str(v).strip() for v in skills_section if str(v).strip()]
        elif isinstance(skills_section, dict):
            values = [str(v).strip() for k, v in skills_section.items() if k != 'list' and str(v).strip()]
        elif isinstance(skills_section, str) and skills_section.strip():
            values = [skills_section.strip()]

        _state['skills_list'] = values

    return _state['skills_list']


def get_skills_content():
    """Read selected skill files and return combined markdown content."""
    if _state['skills_content'] is None:
        get_tools()
        available_capabilities = _collect_available_tool_capabilities(get_tools_metadata())
        blocks = []
        unavailable = []

        for skill_ref in get_skills():
            skill_file = _load_skill_file(skill_ref)
            if skill_file is None:
                unavailable.append({
                    'skill': skill_ref,
                    'reason': 'skill_file_not_found',
                    'missing_required_mcp_tools': [],
                })
                print(f'Warning: skill file not found for ref: {skill_ref}')
                continue

            try:
                raw = skill_file.read_text(encoding='utf-8')
            except Exception as exc:
                unavailable.append({
                    'skill': skill_ref,
                    'reason': f'skill_read_error: {exc}',
                    'missing_required_mcp_tools': [],
                })
                print(f'Warning: failed to read skill file {skill_file}: {exc}')
                continue

            metadata, body = _parse_markdown_frontmatter(raw)
            required = metadata.get('required_mcp_tools') if isinstance(metadata, dict) else []
            if not isinstance(required, list):
                required = []

            missing = []
            for req in required:
                req_value = str(req).strip()
                if not req_value:
                    continue
                if req_value not in available_capabilities:
                    missing.append(req_value)

            skill_id = str(metadata.get('id') or Path(skill_ref).stem)
            skill_name = str(metadata.get('name') or skill_id)

            if missing:
                unavailable.append({
                    'skill': skill_id,
                    'name': skill_name,
                    'file': str(skill_file),
                    'reason': 'missing_required_mcp_tools',
                    'missing_required_mcp_tools': missing,
                })
                print(
                    f'Warning: skipping skill {skill_id} due to missing required_mcp_tools: {missing}'
                )
                continue

            blocks.append(
                f'## {skill_name} ({skill_id})\n\n'
                f'{body.strip()}'
            )

        _state['skills_content'] = '\n\n'.join(blocks).strip()
        _state['skills_unavailable'] = unavailable

    return _state['skills_content']


def get_unavailable_skills():
    if _state['skills_unavailable'] is None:
        get_skills_content()
    return _state['skills_unavailable'] or []


def get_system_prompt():
    """Compose runtime system prompt from SOUL and selected skills."""
    if _state['system_prompt'] is None:
        soul_content = get_soul_content().strip()
        skills_content = get_skills_content().strip()

        if skills_content:
            _state['system_prompt'] = (
                f'{soul_content}\n\n'
                '# Active runtime skills\n'
                'The following skills are active and should be followed while solving tasks:\n\n'
                f'{skills_content}'
            ).strip()
        else:
            _state['system_prompt'] = soul_content

    return _state['system_prompt']