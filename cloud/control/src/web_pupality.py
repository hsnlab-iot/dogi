import os
import base64
import mimetypes
import importlib
import re
from pathlib import Path

try:
    tomllib = importlib.import_module('tomllib')
except ModuleNotFoundError:
    tomllib = importlib.import_module('tomli')

from flask import Flask, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_socketio import SocketIO, emit

from urllib.parse import urlparse

import threading
import urllib.request
from copy import deepcopy

import config

import mimetypes
# Force the OS to recognize webp files correctly
mimetypes.add_type('image/webp', '.webp')

PORT = 5057
SUPPORTED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'}

config.init()

app = Flask(__name__, static_folder='./static')
#app.config['SECRET_KEY'] = 'secret_key'

socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*", socketio_path='/socket.io/')

# This tells Flask it is behind exactly 1 reverse proxy and 
# forces it to generate correct URLs automatically
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


def _find_image_file(folder_path):
    for entry in sorted(os.listdir(folder_path)):
        candidate = os.path.join(folder_path, entry)
        if not os.path.isfile(candidate):
            continue
        _, ext = os.path.splitext(entry)
        if ext.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            return candidate
    return None


def _image_file_to_data_url(image_path):
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = 'application/octet-stream'

    with open(image_path, 'rb') as f:
        raw = f.read()

    encoded = base64.b64encode(raw).decode('ascii')
    return f'data:{mime_type};base64,{encoded}'


def _load_pupcard_data(config_path):
    with open(config_path, 'rb') as f:
        data = tomllib.load(f)
    pupcard = data.get('pupcard', {})
    if not isinstance(pupcard, dict):
        return {}
    return pupcard


def _load_agent_config(agent_name):
    config_path = Path(config.AGENTS_DIR) / agent_name / 'config.toml'
    if not config_path.is_file():
        return {}
    try:
        with config_path.open('rb') as f:
            loaded = tomllib.load(f)
        if isinstance(loaded, dict):
            return loaded
    except Exception as exc:
        print(f'Failed to load agent config {config_path}: {exc}')
    return {}


def _get_selected_pupality_name():
    selected_file = Path(config.CONFIG_DIR) / 'selected'
    if not selected_file.is_file():
        return ''
    try:
        return selected_file.read_text(encoding='utf-8').strip()
    except Exception as exc:
        print(f'Failed to read selected pupality file {selected_file}: {exc}')
        return ''


def _find_tool_descriptor(tool_ref):
    base = Path(config.TOOLS_DIR) / tool_ref
    candidates = [
        base,
        Path(str(base) + '.yaml'),
        Path(str(base) + '.yml'),
        Path(str(base) + '.json'),
        Path(str(base) + '.toml'),
    ]

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _load_structured_descriptor(path):
    suffix = path.suffix.lower()
    if suffix == '.toml':
        return tomllib.loads(path.read_text(encoding='utf-8'))
    if suffix == '.json':
        import json
        return json.loads(path.read_text(encoding='utf-8'))
    if suffix in ('.yaml', '.yml'):
        try:
            yaml = importlib.import_module('yaml')
        except ModuleNotFoundError:
            return {}
        return yaml.safe_load(path.read_text(encoding='utf-8'))
    return {}


def _parse_skill_frontmatter(markdown_text):
    stripped = markdown_text.strip()
    if not stripped.startswith('---\n'):
        return {}, stripped

    end_idx = stripped.find('\n---\n', 4)
    if end_idx < 0:
        return {}, stripped

    meta_raw = stripped[4:end_idx]
    body = stripped[end_idx + 5:].strip()
    try:
        yaml = importlib.import_module('yaml')
        metadata = yaml.safe_load(meta_raw)
        if not isinstance(metadata, dict):
            metadata = {}
    except Exception:
        metadata = {}
    return metadata, body


def _normalize_capability(text):
    return re.sub(r'[^a-z0-9_\-/]+', '-', str(text or '').strip().lower()).strip('-')


def _collect_tool_capabilities(tool_descriptors):
    capabilities = set()
    for descriptor in tool_descriptors:
        name = str(descriptor.get('name') or '').strip()
        if name:
            capabilities.add(name)

        for tag in descriptor.get('tags', []) or []:
            norm = _normalize_capability(tag)
            if norm:
                capabilities.add(norm)

        for provided in descriptor.get('provided_mcp_tools', []) or []:
            value = str(provided).strip()
            if value:
                capabilities.add(value)
    return capabilities


def _load_soul_for_agent(agent_name, agent_config):
    agent_dir = Path(config.AGENTS_DIR) / agent_name
    prompt_lang = str((agent_config.get('language', {}) or {}).get('prompt') or 'en').strip().lower()[:2]
    candidates = [agent_dir / f'SOUL.{prompt_lang}.md', agent_dir / 'SOUL.en.md']

    for candidate in candidates:
        if candidate.is_file():
            try:
                return candidate.read_text(encoding='utf-8').strip(), str(candidate.name)
            except Exception:
                return '', str(candidate.name)
    return '', ''


def get_pupality_info(agent_name):
    payload = {
        'id': agent_name,
        'name': agent_name,
        'image': '',
        'soul': '',
        'soul_file': '',
        'tools': [],
        'skills_available': [],
        'skills_unavailable': [],
    }

    agent_dir = Path(config.AGENTS_DIR) / agent_name
    if not agent_dir.is_dir():
        return payload

    image_path = _find_image_file(str(agent_dir))
    if image_path:
        payload['image'] = _image_file_to_data_url(image_path)

    agent_config = _load_agent_config(agent_name)
    soul_content, soul_file = _load_soul_for_agent(agent_name, agent_config)
    payload['soul'] = soul_content
    payload['soul_file'] = soul_file

    tool_refs = []
    tools_section = agent_config.get('tools', {})
    if isinstance(tools_section, dict):
        tool_refs = [str(v).strip() for v in tools_section.get('list', []) if str(v).strip()]

    tool_descriptors = []
    for ref in tool_refs:
        descriptor_file = _find_tool_descriptor(ref)
        if not descriptor_file:
            payload['tools'].append({'ref': ref, 'available': False})
            continue

        data = _load_structured_descriptor(descriptor_file)
        if not isinstance(data, dict):
            payload['tools'].append({'ref': ref, 'available': False})
            continue

        data = deepcopy(data)
        data['ref'] = ref
        data['available'] = True
        payload['tools'].append(data)
        tool_descriptors.append(data)

    capabilities = _collect_tool_capabilities(tool_descriptors)

    skill_refs = []
    skills_section = agent_config.get('skills', {})
    if isinstance(skills_section, dict):
        skill_refs = [str(v).strip() for v in skills_section.get('list', []) if str(v).strip()]

    for skill_ref in skill_refs:
        skill_file = Path(config.SKILLS_DIR) / f'{skill_ref}.md'
        if not skill_file.is_file():
            payload['skills_unavailable'].append({
                'id': skill_ref,
                'name': skill_ref,
                'required_mcp_tools': [],
                'missing_required_mcp_tools': [],
                'reason': 'skill_file_not_found',
            })
            continue

        try:
            raw = skill_file.read_text(encoding='utf-8')
        except Exception as exc:
            payload['skills_unavailable'].append({
                'id': skill_ref,
                'name': skill_ref,
                'required_mcp_tools': [],
                'missing_required_mcp_tools': [],
                'reason': f'skill_read_error: {exc}',
            })
            continue

        metadata, _body = _parse_skill_frontmatter(raw)
        skill_id = str(metadata.get('id') or skill_ref)
        skill_name = str(metadata.get('name') or skill_id)
        skill_description = str(metadata.get('description') or '').strip()
        skill_doc_url = str(
            metadata.get('url')
            or metadata.get('link')
            or metadata.get('doc_url')
            or ''
        ).strip()
        skill_content = str(_body or '').strip()
        required = metadata.get('required_mcp_tools') if isinstance(metadata, dict) else []
        if not isinstance(required, list):
            required = []
        required = [str(v).strip() for v in required if str(v).strip()]

        missing = [item for item in required if item not in capabilities]
        if missing:
            payload['skills_unavailable'].append({
                'id': skill_id,
                'name': skill_name,
                'description': skill_description,
                'doc_url': skill_doc_url,
                'content': skill_content,
                'required_mcp_tools': required,
                'missing_required_mcp_tools': missing,
                'reason': 'missing_required_mcp_tools',
            })
        else:
            payload['skills_available'].append({
                'id': skill_id,
                'name': skill_name,
                'description': skill_description,
                'doc_url': skill_doc_url,
                'content': skill_content,
                'required_mcp_tools': required,
            })

    return payload


def discover_pupalities():
    pupalities = []
    config_root = config.AGENTS_DIR

    if not os.path.isdir(config_root):
        print(f'Agents folder not found: {config_root}')
        return pupalities

    for current_root, dirs, _files in os.walk(config_root):
        # We only care about folder-based pupality packs below config root.
        if current_root == config_root:
            continue

        pack_config_path = os.path.join(current_root, 'config.toml')
        if not os.path.isfile(pack_config_path):
            continue

        image_path = _find_image_file(current_root)
        if not image_path:
            print(f'Skipping pupality folder without image: {current_root}')
            continue

        try:
            pupcard = _load_pupcard_data(pack_config_path)
            name = str(pupcard.get('name') or os.path.basename(current_root))
            language = str(pupcard.get('language') or '')
            llm_model = str(pupcard.get('model') or '')
            tts_name = str(pupcard.get('tts') or '')
            image_data_url = _image_file_to_data_url(image_path)
        except Exception as exc:
            print(f'Failed to load pupality from {current_root}: {exc}')
            continue

        pupalities.append({
            'id': os.path.basename(current_root),
            'name': name,
            'image': image_data_url,
            'language': language,
            'llm_model': llm_model,
            'tts': tts_name,
        })

        # This pack is complete, no need to walk deeper under it.
        dirs[:] = []

    pupalities.sort(key=lambda item: item['name'].lower())
    return pupalities


PUPALITIES_CACHE = discover_pupalities()
print(f'Loaded pupalities: {len(PUPALITIES_CACHE)}')

@app.route('/')
def index():
    host = urlparse(request.url_root).hostname
    return render_template('web_pupality.html', host=host)

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('pupalities', {
        'data': PUPALITIES_CACHE,
        'selected': _get_selected_pupality_name(),
    })

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')


@socketio.on('refresh_pupalities')
def handle_refresh_pupalities():
    global PUPALITIES_CACHE
    PUPALITIES_CACHE = discover_pupalities()
    socketio.emit('pupalities', {
        'data': PUPALITIES_CACHE,
        'selected': _get_selected_pupality_name(),
    })
    print(f'Refreshed pupalities: {len(PUPALITIES_CACHE)}')


@socketio.on('pupality_info')
def handle_pupality_info(payload):
    if not isinstance(payload, dict):
        payload = {}

    agent_name = str(payload.get('name') or '').strip()
    if not agent_name:
        emit('pupality_info', {'name': '', 'error': 'missing_name'})
        return

    emit('pupality_info', get_pupality_info(agent_name))

@socketio.on('pupality_select')
def handle_pupality_select(payload):
    if not isinstance(payload, dict):
        payload = {}

    selected_name = str(payload.get('name') or '')

    print(
        'Selected pupality:', selected_name
    )
    config.reinit(selected_name)

    def _reload_web_main():
        try:
            with urllib.request.urlopen('http://localhost:5059/reload', timeout=5) as resp:
                print(f'web_main reload response: {resp.status}')
        except Exception as exc:
            print(f'web_main reload error: {exc}')

    threading.Thread(target=_reload_web_main, daemon=True).start()


def handle_error(e):
    print('SocketIO Error:', e)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=PORT)
