import os

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import pickle
import socket
import time
import threading
from urllib.parse import urlparse

import config
import utils
import base64
from io import BytesIO
from PIL import Image

PORT = 5056

config.init()

app = Flask(__name__)
#app.config['SECRET_KEY'] = 'secret_key'
socketio = SocketIO(app)
socketio.init_app(app, cors_allowed_origins="*")

# Worker control
worker_lock = threading.Lock()
worker_thread = None
worker_stop_event = None

@app.route('/')
def index():
    host = urlparse(request.url_root).hostname
    return render_template('web_prompt.html', host=host)

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('prompt')
def handle_event(data):
    """Start a worker thread to handle the prompt call to the OpenAI-compatible server.
    Expected `data` keys: { prompt: str, tools: [str,...] }
    The worker can be stopped by emitting a 'stop_prompt' event.
    """
    global worker_thread, worker_stop_event
    prompt_text = ''
    tools = []
    try:
        prompt_text = data.get('prompt', '') if isinstance(data, dict) else str(data)
        tools = data.get('tools', []) if isinstance(data, dict) else []
    except Exception:
        prompt_text = str(data)

    with worker_lock:
        if worker_thread and worker_thread.is_alive():
            # already running; ignore or inform client
            socketio.emit('ui_update_reponse', {'status': 'busy'})
            return

        # create a stop event for this worker
        worker_stop_event = threading.Event()

        def prompt_worker(prompt_text, tools, stop_event):
            """Worker: call utils.prompt with the prompt_text and tools, emit results.
            Placeholder hooks for tool-calls are included.
            """
            try:
                # Prepare prompt content: include tools list
                tools_list = ', '.join(tools) if tools else ''
                if tools_list:
                    prompt_with_tools = f"Available tools: {tools_list}\n\n{prompt_text}"
                else:
                    prompt_with_tools = prompt_text

                # Notify client that work started
                socketio.emit('ui_update_reponse', {'status': 'started'})

                # Call the prompt (blocking)
                # For future: switch to streaming mode to update reasoning progressively
                response_text = utils.prompt(prompt_with_tools)

                # Check stop flag before emitting
                if stop_event.is_set():
                    socketio.emit('ui_update_reponse', {'status': 'stopped'})
                    return

                # Emit final response (response_text). reasoning currently not separated.
                socketio.emit('ui_update_reponse', {'status': 'done', 'response': response_text})

            except Exception as e:
                socketio.emit('ui_update_reponse', {'status': 'error', 'error': str(e)})
            finally:
                # clear worker globals
                with worker_lock:
                    nonlocal_worker = globals()
                    try:
                        # mark thread finished
                        pass
                    except Exception:
                        pass

        # start the worker thread
        worker_thread = threading.Thread(target=prompt_worker, args=(prompt_text, tools, worker_stop_event), daemon=True)
        worker_thread.start()
        socketio.emit('ui_update_reponse', {'status': 'started'})

@socketio.on('tools')
def handle_event(data):
    socketio.emit('ui_update_tools', data)

@socketio.on('reload')
def handle_event(data):
    pass


@socketio.on('stop_prompt')
def handle_stop(data):
    """Signal the running worker to stop."""
    global worker_thread, worker_stop_event
    with worker_lock:
        if worker_thread and worker_thread.is_alive() and worker_stop_event:
            worker_stop_event.set()
            socketio.emit('ui_update_reponse', {'status': 'stopping'})
        else:
            socketio.emit('ui_update_reponse', {'status': 'no_worker'})

@socketio.on_error()  # Handle socketio errors
def handle_error(e):
    print('SocketIO Error:', e)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=PORT)
