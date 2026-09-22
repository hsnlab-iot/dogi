import os
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from urllib.parse import urlparse, urljoin
import urllib.request
import urllib.parse
import libtmux
import config
import ollama_runtime
import time
import threading
import socket
import errno
import json
from datetime import datetime, timezone

import utils
import config

PORT = 5059

config.init()

app = Flask(__name__)

socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*")


@app.after_request
def _add_status_api_cors_headers(response):
    path = str(request.path or '')
    if path.startswith('/api/status'):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

session = None

_ping_lock = threading.Lock()
_ping_state = {
    'sequence': 0,
    'timestamp': 0.0,
    'timestamp_iso': '',
    'robot_ip': '',
    'port': 56789,
    'timeout_seconds': 3.0,
    'rtt_ms': -1.0,
    'status': 'init',
    'error': '',
}


def _utc_iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _syn_rst_ping_once(robot_ip, port=56789, timeout_seconds=3.0):
    started = time.monotonic()
    if not robot_ip:
        return -1.0, 'unavailable', 'ROBOT_IP is not defined'

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(float(timeout_seconds))
        result = sock.connect_ex((robot_ip, int(port)))
        elapsed_ms = (time.monotonic() - started) * 1000.0

        # Closed port => RST -> connection refused (expected for SYN-RST timing).
        if result == errno.ECONNREFUSED:
            return round(elapsed_ms, 3), 'rst', ''

        # Open port is not a SYN-RST result for this test.
        if result == 0:
            return -1.0, 'unexpected_open', 'port is open, expected RST on closed port'

        # Timeout/unreachable or any other error => unavailable.
        return -1.0, 'unavailable', f'connect_ex={result}'
    except socket.timeout:
        return -1.0, 'timeout', 'timeout'
    except Exception as exc:
        return -1.0, 'error', str(exc)
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _ping_worker_loop(interval_seconds=1.0):
    period = max(0.2, float(interval_seconds))

    while True:
        started_wall = time.time()
        robot_ip = str(os.environ.get('ROBOT_IP') or '').strip()
        port = 56789
        timeout_seconds = 3.0

        rtt_ms, status, error_text = _syn_rst_ping_once(
            robot_ip,
            port=port,
            timeout_seconds=timeout_seconds,
        )

        finished = time.time()
        with _ping_lock:
            _ping_state['sequence'] += 1
            _ping_state['timestamp'] = finished
            _ping_state['timestamp_iso'] = _utc_iso(finished)
            _ping_state['robot_ip'] = robot_ip
            _ping_state['port'] = port
            _ping_state['timeout_seconds'] = timeout_seconds
            _ping_state['rtt_ms'] = float(rtt_ms)
            _ping_state['status'] = status
            _ping_state['error'] = str(error_text or '')

        elapsed = finished - started_wall
        sleep_seconds = period - elapsed
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)


_ping_thread = threading.Thread(target=_ping_worker_loop, daemon=True)
_ping_thread.start()

pageconfig = [ \
    { 'name': 'Search', 'port': PORT, 'page': '/apps/search/', 'app': '/app/keresd.py' }, \
    { 'name': 'Follow', 'port': PORT, 'page': '/apps/follow/', 'app': '/app/kovesd.py' }, \
    { 'name': 'Show', 'port': PORT, 'page': '/apps/show/', 'app': '/app/mutasd.py' }, \
    { 'name': 'Prompt', 'port': PORT, 'page': '/apps/prompt/', 'app': '/app/prompt.py' }, \
    { 'name': 'Pupality', 'port': PORT, 'page': '/apps/pupality/', 'app': '' }, \
    { 'name': 'System', 'port': PORT, 'page': '/apps/system/', 'app': '' } \
]

@app.route('/')
def index():
    context = {
        'page0_name': pageconfig[0]['name'],
        'page1_name': pageconfig[1]['name'],
        'page2_name': pageconfig[2]['name'],
        'page3_name': pageconfig[3]['name'],
        'page4_name': pageconfig[4]['name'],
        'page5_name': pageconfig[5]['name'],
    }
    return render_template('web_main.html', **context)


def _get_victoria_query_url():
    """Return the VictoriaMetrics base query URL, or None if not configured."""
    base = os.environ.get('VICTORIA_BASE_URL', '').strip()
    if not base:
        return None
    return base.rstrip('/')


def _get_ping_snapshot():
    with _ping_lock:
        return dict(_ping_state)


def _fetch_stream_stats(host, timeout_seconds=1.0):
    url = f'http://{host}:5051/stats'
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            payload = resp.read().decode('utf-8')
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError('invalid stats payload')
        data['ok'] = True
        data['source'] = url
        return data
    except Exception as exc:
        return {
            'ok': False,
            'source': url,
            'error': str(exc),
            'fps': 0.0,
            'bitrate_bps': 0.0,
            'bitrate_mbps': 0.0,
            'resolution': {'width': 0, 'height': 0, 'label': 'unknown'},
            'sample_count': 0,
            'window_seconds': 0.0,
        }


def _flatten_ollama_models(ollama_status):
    flat = []
    servers = ollama_status.get('servers') if isinstance(ollama_status, dict) else []
    if not isinstance(servers, list):
        return flat

    for server in servers:
        if not isinstance(server, dict):
            continue
        server_url = str(server.get('server_url') or '')
        ps_models = server.get('ps_models') if isinstance(server.get('ps_models'), list) else []
        for model in ps_models:
            if not isinstance(model, dict):
                continue
            row = dict(model)
            row['server_url'] = server_url
            flat.append(row)

    return flat


@app.route('/api/status')
def api_status():
    """Return aggregated runtime status for streamer, ollama models and ping."""
    host = urlparse(request.url_root).hostname or 'localhost'

    streamer = _fetch_stream_stats(host, timeout_seconds=1.0)
    ping = _get_ping_snapshot()

    try:
        ollama_payload = ollama_runtime.get_runtime_status(include_ps=True)
    except Exception as exc:
        ollama_payload = {
            'server_count': 0,
            'servers': [],
            'owner_to_server': {},
            'updated_at': time.time(),
            'error': str(exc),
        }

    ollama_models = _flatten_ollama_models(ollama_payload)

    fps = float(streamer.get('fps') or 0.0)
    ping_rtt = float(ping.get('rtt_ms') or -1.0)
    model_count = len(ollama_models)

    status_parts = [
        f'Stream FPS: {fps:.2f}',
        f'Ping: {ping_rtt:.2f} ms' if ping_rtt >= 0 else 'Ping: -1',
        f'Ollama models: {model_count}',
    ]

    return jsonify({
        'status': ' | '.join(status_parts),
        'statusHTML': ' | '.join(status_parts),
        'timestamp': time.time(),
        'streamer': streamer,
        'ping': ping,
        'ollama': ollama_payload,
        'ollama_models': ollama_models,
    })


@app.route('/api/status/ollama')
def api_ollama_status():
    """Return live Ollama runtime worker status including /api/ps model state."""
    include_ps_arg = str(request.args.get('include_ps', '1')).strip().lower()
    include_ps = include_ps_arg in ('1', 'true', 'yes', 'on')

    try:
        return jsonify(ollama_runtime.get_runtime_status(include_ps=include_ps))
    except Exception as exc:
        return jsonify({'status': 'error', 'error': str(exc)}), 500

@app.route('/api/status/ping')
def api_ping_status():
    with _ping_lock:
        payload = dict(_ping_state)
    return jsonify(payload)


@app.route('/api/status/hf')
def api_hf_status():
    offline1 = os.getenv("HF_HUB_OFFLINE") or ""
    offline2 = os.getenv("TRANSFORMERS_OFFLINE") or ""
    if offline1 == "1" and offline2 == "1":
        return {'status': 'offline'}
    else:
        return {'status': 'online'}

@app.route('/reload', methods=['POST', 'GET'])
def reload_config():
    try:
        config.reinit()
        return {'status': 'ok', 'message': 'configuration reloaded'}, 200
    except Exception as exc:
        return {'status': 'error', 'message': str(exc)}, 500

@socketio.on('page_change')
def handle_event(data):
    global session

    print('received message: ' + str(data))
    host = urlparse(request.url_root).hostname
    page = 'http://' + host + ':' + str(pageconfig[data]['port']) + pageconfig[data]['page']
    print('URL: ', page)
    socketio.emit('page_load', page)

    if session is not None:
        session.kill()
        session = None

    if pageconfig[data]['app'] != '':
        server = libtmux.Server()
        session = server.new_session(session_name='dogi_session', kill=True)
        window = session.new_window(attach=True)
        pane = window.active_pane
        pane.send_keys(f'cd; source /opt/venv/bin/activate && python {pageconfig[data]["app"]}; sleep inf')
        
@app.route('/voice/<path:filename>')
def voice_file(filename):
    filepath = os.path.join(config.get_cache_dir(), 'voice')
    os.makedirs(filepath, exist_ok=True)
    return send_from_directory(filepath, filename)

@app.route('/voice/init')
def voiceinit():
    prompt_text = config.get_prompt('web_voice', 'test_init_1')
    prompt_text = utils.select_text(prompt_text,  config.get_ui_language(), True)
    funny, _ = utils.prompt(prompt_text)
    if config.needs_translation():
        funny = utils.translate(funny, config.get_prompt_language())

    welcome_text = {
        "en": "Hello. I am Dogi, a robot dog from BME.",
        "hu": "Szia. Dogi vagyok, egy robotkutya a BME-ről."
    }
    welcome_text = utils.select_text(welcome_text, config.get_ui_language(), True)
    wt, d = utils.tts_wav(welcome_text)
    socketio.emit('audio_play', wt)
    time.sleep(d)

    ft, d = utils.tts_wav(funny)
    socketio.emit('audio_play', ft)

    return "", 200

@socketio.on('audio_play_proxy')
def audio_play(data):
    print('Request for audio play')
    socketio.emit('audio_play', data)


@socketio.on_error()  # Handle socketio errors
def handle_error(e):
    print('SocketIO Error:', e)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=PORT)