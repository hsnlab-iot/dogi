import os
import base64
import mimetypes
import importlib

try:
    tomllib = importlib.import_module('tomllib')
except ModuleNotFoundError:
    tomllib = importlib.import_module('tomli')

from flask import Flask, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_socketio import SocketIO, emit

from urllib.parse import urlparse

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


def discover_pupalities():
    pupalities = []
    config_root = config.CONFIG_DIR

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
    emit('pupalities', PUPALITIES_CACHE)

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')


@socketio.on('refresh_pupalities')
def handle_refresh_pupalities():
    global PUPALITIES_CACHE
    PUPALITIES_CACHE = discover_pupalities()
    socketio.emit('pupalities', PUPALITIES_CACHE)
    print(f'Refreshed pupalities: {len(PUPALITIES_CACHE)}')


@socketio.on('pupality_select')
def handle_pupality_select(payload):
    if not isinstance(payload, dict):
        payload = {}

    selected_name = str(payload.get('name') or '')

    print(
        'Selected pupality:', selected_name
    )


@socketio.on_error()  # Handle socketio errors
def handle_error(e):
    print('SocketIO Error:', e)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=PORT)
