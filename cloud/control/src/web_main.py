import os
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from urllib.parse import urlparse, urljoin
import urllib.request
import urllib.parse
import libtmux
import config
import time

import utils
import config

PORT = 5059

config.init()

app = Flask(__name__)

socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*")

session = None

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


@app.route('/api/status')
def api_status():
    """Query VictoriaMetrics for current streaming state and return it as JSON."""
    victoria_base = _get_victoria_query_url()
    if not victoria_base:
        return jsonify({'status': 'victoria not configured', 'error': 'victoria not configured'})

    try:
        import json

        def run_query(query, timeout=3):
            # Generic instant query with nocache=1
            params = urllib.parse.urlencode({'query': query, 'nocache': '1'})
            url = f"{victoria_base}/api/v1/query?{params}"
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode('utf-8')
                return json.loads(raw), raw

        def build_query(state):
            return f'last_over_time({state}[90s]) and topk(1, tlast_over_time({state}[90s]))'

        # streaming state: use last_over_time over the last 90s; missing -> OFF
        streaming = None
        raw_streaming = None
        try:
            data_tlast, raw_streaming = run_query(build_query('streamer_state_streaming'))
            results = data_tlast.get('data', {}).get('result', [])
            if results:
                value = results[0].get('value', [None, None])[1]
                try:
                    streaming = int(float(value)) == 1
                except (TypeError, ValueError):
                    streaming = None
            else:
                streaming = False
        except Exception:
            streaming = None

        # ollama GPU utilization (may contain multiple models)
        gpu_parts = []
        raw_ollama = None
        try:
            data_tlast, raw_ollama = run_query(build_query('ollama_state_gpu_utilization'))
            results = data_tlast.get('data', {}).get('result', [])
            if results:
                for r in results:
                    metric = r.get('metric', {})
                    model = metric.get('model') or metric.get('name') or metric.get('__name__')
                    value = r.get('value', [None, None])[1]
                    if value is None:
                        pct = 0
                    else:
                        try:
                            pct = int(round(float(value)))
                        except Exception:
                            pct = -1
                    gpu_parts.append((model, pct))
        except Exception:
            pass

        def color_span(text, color):
            return f"<span style=\"color:{color}\">{text}</span>"

        # build streamer text and HTML
        if streaming:
            stream_text = 'ON'
            stream_color = 'green'
        else:
            stream_text = 'OFF'
            stream_color = 'red'

        status_parts = [f"Streamer: {stream_text}"]
        status_html_parts = ["Streamer: " + color_span(stream_text, stream_color)]

        # ensure at least a default ollama entry
        if not gpu_parts:
            gpu_parts = [("none", 0)]

        # append ollama/model parts
        for model, pct in gpu_parts:
            model_display = model or 'none'
            pct_display = pct if pct is not None and pct >= 0 else 0
            # colors: model green if name exists (not 'none'), else red; gpu green only at 100%
            gpu_color = 'green' if pct_display == 100 else 'red'

            status_parts.append(f"{model_display} GPU: {pct_display}%")
            status_html_parts.append(f"{model_display} GPU: {color_span(str(pct_display), gpu_color)}%")

        return jsonify({
            'status': ' - '.join(status_parts),
            'statusHTML': ' - '.join(status_html_parts),
            'streamingResponse': raw_streaming,
            'ollamaResponse': raw_ollama,
        })
    except Exception as exc:
        return jsonify({'status': 'Error', 'error': str(exc)})


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