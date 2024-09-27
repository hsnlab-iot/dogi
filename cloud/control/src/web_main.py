from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from urllib.parse import urlparse
import libtmux

app = Flask(__name__)

socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*")

session = None

pageconfig = [ \
    { 'name': 'Keresd!', 'port': 5053, 'page': '/', 'app': 'keresd.py' }, \
    { 'name': 'Kovesd!', 'port': 5055, 'page': '/', 'app': 'kovesd.py' }, \
    { 'name': 'Mutasd!', 'port': 5054, 'page': '/', 'app': 'mutasd.py' }, \
    { 'name': 'system', 'port': 5050, 'page': '/', 'app': '' } \
]

@app.route('/')
def index():
    context = {
        'page0_name': pageconfig[0]['name'],
        'page1_name': pageconfig[1]['name'],
        'page2_name': pageconfig[2]['name'],
        'page3_name': pageconfig[3]['name'],
    }
    return render_template('web_main.html', **context)

@socketio.on('page_change')
def handle_event(data):
    global session

    print('received message: ' + str(data))
    host = urlparse(request.url_root).hostname
    page = 'http://' + host + ':' + str(pageconfig[data]['port']) + pageconfig[data]['page']
    print('URL: ', page)
    socketio.emit('page_load', page)

    if session is not None:
        session.kill_session()
        session = None

    if pageconfig[data]['app'] != '':
        server = libtmux.Server()
        session = server.new_session(session_name='dogi_session', kill_session=True)
        window = session.new_window(attach=True)
        pane = window.active_pane
        pane.send_keys(f'cd; source .yolo/bin/activate && python {pageconfig[data]["app"]}; sleep inf')
        
    
@socketio.on_error()  # Handle socketio errors
def handle_error(e):
    print('SocketIO Error:', e)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5059)