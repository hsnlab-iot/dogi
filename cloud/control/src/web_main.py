import os
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from urllib.parse import urlparse, urljoin
import urllib.request
import urllib.parse
import libtmux
import config

PORT = 5059

app = Flask(__name__)

socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*")

session = None

pageconfig = [ \
    { 'name': 'Keresd!', 'port': 5053, 'page': '/', 'app': '/app/keresd.py' }, \
    { 'name': 'Kovesd!', 'port': 5055, 'page': '/', 'app': '/app/kovesd.py' }, \
    { 'name': 'Mutasd!', 'port': 5054, 'page': '/', 'app': '/app/mutasd.py' }, \
    { 'name': 'Parancs', 'port': 5056, 'page': '/', 'app': '/app/prompt.py' }, \
    { 'name': 'system', 'port': 5050, 'page': '/', 'app': '' } \
]

@app.route('/')
def index():
    context = {
        'page0_name': pageconfig[0]['name'],
        'page1_name': pageconfig[1]['name'],
        'page2_name': pageconfig[2]['name'],
        'page3_name': pageconfig[3]['name'],
        'page4_name': pageconfig[4]['name'],
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
        return jsonify({'streaming': None, 'error': 'victoria not configured'})

    try:
        query = 'streamer_state_streaming'
        params = urllib.parse.urlencode({'query': query})
        url = f"{victoria_base}/api/v1/query?{params}"
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=3) as resp:
            import json
            data = json.loads(resp.read().decode('utf-8'))

        results = data.get('data', {}).get('result', [])
        if results:
            value = results[0].get('value', [None, None])[1]
            try:
                streaming = int(float(value)) == 1
            except (TypeError, ValueError):
                streaming = None
        else:
            streaming = None

        return jsonify({'streaming': streaming})
    except Exception as exc:
        return jsonify({'streaming': None, 'error': str(exc)})


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
        
    
@socketio.on_error()  # Handle socketio errors
def handle_error(e):
    print('SocketIO Error:', e)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=PORT)