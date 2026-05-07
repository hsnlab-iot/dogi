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
import asyncio

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
    global worker_thread, worker_stop_event, openai_tools, tools
    try:
        prompt_text = data.get('prompt', '') if isinstance(data, dict) else str(data)
    except Exception:
        prompt_text = str(data)

    with worker_lock:
        if worker_thread and worker_thread.is_alive():
            sio.emit('ui_update_reponse', {'status': 'busy'})
            return

        # set up stop event for this worker
        worker_stop_event = threading.Event()

        def worker(prompt_text, openai_tools, tools, stop_event):
            try:
                sio.emit('ui_update_reponse', {'status': 'started'})

                tool_calls = True
                prompt = prompt_text
                while (tool_calls):
                    # Call the prompt (blocking). In future we can use stream=True to send partial updates.                    
                    messages, response = utils.prompt(prompt, tools = openai_tools)
                    response_message = response.choices[0].message
                    tool_calls = response_message.tool_calls

                    print("Message content:")
                    print(response_message.content)
                    prompt = messages
                    prompt.append(response_message)
                    if tool_calls:
                        for tool_call in tool_calls:
                            function_name = tool_call.function.name
                            function_args = json.loads(tool_call.function.arguments)                            
                            print(f"Calling tool {function_name}")

                            for tool in tools:
                                if tool[1] == function_name:
                                    print(tool[0])
                                    rmcp = tool[0]
                                    print("Calling the tool")
                                    result = rmcp.call_tool_blocking(function_name, function_args)
                                    print(f"Result: {result}")
                                    prompt.append({
                                        "tool_call_id": tool_call.id,
                                        "role": "tool",
                                        "name": function_name,
                                        "content": result,
                                    })
                        
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

        worker_thread = threading.Thread(target=worker, args=(prompt_text, openai_tools, tools, worker_stop_event), daemon=True)
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
                rmcp.ssh_connect(user, ip, python_path, script_path)
                mcp_tools = rmcp.get_tools_blocking()
                
            elif kind == 'sse':
                # rest is like "http://ip:port/test"
                url = rest
                
                rmcp = RemoteMCPManager.RemoteMCPManager()
                rmcp.sse_connect(url)
                mcp_tools = rmcp.get_tools_blocking()

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
    sio.emit('ui_update', {'type': 'tools', 'data': xtools})
    sio.emit('ui_update', {'type': 'prompt', 'data': 'prompt'})
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
