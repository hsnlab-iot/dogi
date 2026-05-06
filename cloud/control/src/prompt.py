import cv2
import numpy as np
import zmq
import time
import socket
import pickle
import threading
import random
from io import BytesIO
import os
import glob
import subprocess
import urllib.request
import json

import utils
import config
import RemoteMCPManager

import socketio

PORT = 5056

DEBUG_mode = os.getenv('DEBUG', '0') == '1'
sio = socketio.Client()

config.init()
toolscfg = config.get_tools()
tools = []
openai_tools = []

# Worker control globals
worker_lock = threading.Lock()
worker_thread = None
worker_stop_event = None

@sio.event
def connect():
    print("Connected to Flask server!")

@sio.on('client_prompt')
def handle_prompt(data):
    """Start a background worker to call the OpenAI-compatible server with the prompt.
    data can be a dict with keys: { prompt: str, tools: [toolName,...] }
    The worker emits status updates via sio.emit('ui_update_reponse', {...}).
    """
    global worker_thread, worker_stop_event
    try:
        prompt_text = data.get('prompt', '') if isinstance(data, dict) else str(data)
        tools_list = data.get('tools', []) if isinstance(data, dict) else []
    except Exception:
        prompt_text = str(data)
        tools_list = []

    with worker_lock:
        if worker_thread and worker_thread.is_alive():
            sio.emit('ui_update_reponse', {'status': 'busy'})
            return

        # set up stop event for this worker
        worker_stop_event = threading.Event()

        def worker(prompt_text, tools_list, stop_event):
            try:
                sio.emit('ui_update_reponse', {'status': 'started'})

                # Prepare the prompt to include available tools (for now as text)
                tools_text = ''
                if tools_list:
                    if isinstance(tools_list, dict) and 'data' in tools_list:
                        # some callers send {data: [...]}
                        tnames = tools_list.get('data') or []
                    else:
                        tnames = tools_list
                    tools_text = 'Available tools: ' + ', '.join(tnames) + '\n\n'

                prompt_with_tools = tools_text + prompt_text

                # Call the prompt (blocking). In future we can use stream=True to send partial updates.
                response_text = utils.prompt(prompt_with_tools)

                # If stop requested, don't emit final result
                if stop_event.is_set():
                    sio.emit('ui_update_reponse', {'status': 'stopped'})
                    return

                sio.emit('ui_update_reponse', {'status': 'done', 'response': response_text})

            except Exception as e:
                sio.emit('ui_update_reponse', {'status': 'error', 'error': str(e)})
            finally:
                # clear worker globals
                with worker_lock:
                    nonlocal_vars = globals()
                    try:
                        # mark worker as finished by clearing event/thread
                        nonlocal_vars['worker_thread'] = None
                        nonlocal_vars['worker_stop_event'] = None
                    except Exception:
                        pass

        worker_thread = threading.Thread(target=worker, args=(prompt_text, tools_list, worker_stop_event), daemon=True)
        worker_thread.start()
        sio.emit('ui_update_reponse', {'status': 'spawned'})

def connec_MCP_serves():    
    # Connect to MCP serves

    robot_ip = os.getenv('ROBOT_IP', '127.0.0.1')

    for mcp_server in toolscfg:
        try:
            if not isinstance(mcp_server, str) or '!' not in mcp_server:
                print('invalid mcp_server entry:', mcp_server)
                continue

            kind, rest = mcp_server.split('!', 1)

            rcmp = None
            mcp_tools = None

            if kind == 'ssh':
                # rest is like "user@ip:~/venv/bin/python3:~/test.py"
                user, python_path, script_path = rest.split(':', 2)
                ip = robot_ip
                if '@' in user:
                    user, ip = user.split('@', 1)

                # RemoteMCPManager is a module; instantiate the class inside it
                rmcp = RemoteMCPManager.RemoteMCPManager()
                rmcp.connect(user, ip, python_path, script_path)
                mcp_tools = rmcp.get_tools_blocking()
                
            elif kind == 'sse':
                # rest is like "5000/test" -> port and path
                if '/' not in rest:
                    print('sse entry missing path:', mcp_server)
                    continue
                port_str, url_path = rest.split('/', 1)
                port = port_str.strip()
                path = '/' + url_path.lstrip('/')
                url = f"http://{robot_ip}:{port}{path}"
                try:
                    with urllib.request.urlopen(url, timeout=10) as resp:
                        body = resp.read().decode('utf-8')
                    # try parse json with url field, else take body as unique url
                    unique = None
                    try:
                        j = json.loads(body)
                        unique = j.get('url') or j.get('unique') or j.get('data')
                    except Exception:
                        unique = body.strip()

                    toolname = path.rstrip('/').split('/')[-1]
                    tools.append({'type': 'sse', 'name': toolname, 'port': port, 'path': path, 'url': unique})
                    print('sse tool registered:', toolname)
                except Exception as e:
                    print('failed to contact sse tool', mcp_server, e)
            else:
                print('unknown tool kind:', kind)
                continue

            try:
                for tool in mcp_tools.tools:
                    print(tool)
                    openai_tools.append(
                        {
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description,
                                "parameters": tool.inputSchema,
                            },
                        }
                    )
                    tools.append(
                        (rmcp, tool.name, tool.description)
                    )
            except Exception as e:
                print('failed to parse mcp_tools list:', e)
            
        except Exception as e:
            print('error processing mcp_server', mcp_server, e)

        print(f"Found tools: {tools}")

def introduction():
    text = {
        'en': "Give me a prompt, and I will do it!",
        'hu': "Adj egy utasítást, és én végrehajtom!"
    }
    xtext = utils.select_text(text, config.get_ui_language(), True)
    print(xtext)
    wav, d = utils.tts_wav(xtext, config.get_ui_language() + "_intro_keresd")
    utils.play_wav(wav)
    time.sleep(d)

if __name__ == '__main__':
    # Connect to your Flask-SocketIO address
    sio.connect(f'http://localhost:{PORT}') 

    connec_MCP_serves()

    xtools = [] 
    for tool in tools:
        xtools.append(tool[1])
    sio.emit('tools', {'data': xtools})

    utils.dogy_reset()
    introduction()

    sio.wait()


@sio.on('stop_prompt')
def handle_stop(data=None):
    """Signal the running worker to stop."""
    global worker_thread, worker_stop_event
    with worker_lock:
        if worker_thread and worker_thread.is_alive() and worker_stop_event:
            worker_stop_event.set()
            sio.emit('ui_update_reponse', {'status': 'stopping'})
        else:
            sio.emit('ui_update_reponse', {'status': 'no_worker'})
