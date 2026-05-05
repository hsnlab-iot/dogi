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

PORT = 5056

DEBUG_mode = os.getenv('DEBUG', '0') == '1'

config.init()

# Create a UDP sockets to web page server
sock_web = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock_web.connect(('localhost', PORT))

# Connect to MCP serves
toolscfg = config.get_tools()
tools = []

robot_ip = os.getenv('ROBOT_IP', '127.0.0.1')

for mcp_server in toolscfg:
    try:
        if not isinstance(mcp_server, str) or '@' not in mcp_server:
            print('invalid mcp_server entry:', mcp_server)
            continue

        kind, rest = mcp_server.split('@', 1)

        if kind == 'ssh':
            # rest is like "user:~/venv/bin/python3:~/test.py"
            if ':' not in rest:
                print('ssh entry missing path:', mcp_server)
                continue
            user, python_path, script_path = rest.split(':', 2)

            # RemoteMCPManager is a module; instantiate the class inside it
            rmcp = RemoteMCPManager.RemoteMCPManager()
            rmcp.connect(robot_ip, user, python_path, script_path)
            mcp_tools = rmcp.get_tools_blocking()
            print(f"Found tools: {mcp_tools}")
            tools.append((rmcp, mcp_tools))
            
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
    except Exception as e:
        print('error processing mcp_server', mcp_server, e)

text = {
    'en': "Give me a prompt, and I will do it!",
    'hu': "Adj egy utasítást, és én végrehajtom!"
}
xtext = utils.select_text(text, config.get_ui_language(), True)
print(xtext)
wav, d = utils.tts_wav(xtext, config.get_ui_language() + "_intro_keresd")
utils.play_wav(wav)
time.sleep(d)

utils.dogy_reset()

while True:
    time.sleep(1)

