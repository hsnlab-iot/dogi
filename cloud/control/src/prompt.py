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
        if not isinstance(mcp_server, str) or '!' not in mcp_server:
            print('invalid mcp_server entry:', mcp_server)
            continue

        kind, rest = mcp_server.split('!', 1)

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

        # Normalize tools: extract `name` and `description` when available
        parsed_tools = []
        try:
            for t in mcp_tools:
                name = None
                desc = ''
                # dict-like
                if isinstance(t, dict):
                    for k in ('name', 'tool', 'id', 'title'):
                        if k in t and t[k]:
                            name = str(t[k])
                            break
                    for k in ('description', 'desc', 'help', 'details', 'long_description'):
                        if k in t and t[k]:
                            desc = str(t[k])
                            break
                else:
                    # object with attributes (e.g., Tool instances)
                    try:
                        if hasattr(t, 'name') and getattr(t, 'name'):
                            name = str(getattr(t, 'name'))
                        elif hasattr(t, 'title') and getattr(t, 'title'):
                            name = str(getattr(t, 'title'))
                        elif hasattr(t, 'tool') and getattr(t, 'tool'):
                            name = str(getattr(t, 'tool'))

                        if hasattr(t, 'description') and getattr(t, 'description'):
                            desc = str(getattr(t, 'description'))
                        elif hasattr(t, 'desc') and getattr(t, 'desc'):
                            desc = str(getattr(t, 'desc'))
                    except Exception:
                        pass

                    if not name:
                        try:
                            s = str(t)
                            import re
                            m = re.search(r"name=['\"]([^'\"]+)['\"]", s)
                            if m:
                                name = m.group(1)
                            else:
                                name = s.split('(')[0] if '(' in s else s
                        except Exception:
                            name = None

                if not name:
                    name = '<unknown>'

                parsed_tools.append({'name': name, 'description': desc, 'raw': t})
        except Exception as e:
            print('failed to parse mcp_tools list:', e)
            parsed_tools = [{'name': str(mcp_tools), 'description': ''}]


        print(f"Found tools: {mcp_tools}")
        
        # store parsed tools (name/description) for later use
        tools.append((rmcp, parsed_tools))

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

