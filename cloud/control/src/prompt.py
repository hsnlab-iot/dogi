from unittest import result

import numpy as np
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
from concurrent.futures import ThreadPoolExecutor, as_completed

from typing import List, Dict, Any
from mcp.types import CallToolResult, ImageContent, TextContent

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

# History context
message_history = []

def mcp_to_openai_multimodal_tool(mcp_result: CallToolResult, tool_call_id: str) -> Dict[str, Any]:
    """
    Converts MCP result into a multimodal OpenAI tool message.
    The image is contained WITHIN the tool response, linking it to the ID.
    """
    openai_content = []
    texts = []
    image = None

    for item in mcp_result.content:
        if isinstance(item, TextContent):
            openai_content.append({
                "type": "text",
                "text": item.text
            })
            texts.append(item.text)
        elif isinstance(item, ImageContent):
            # Ensure the base64 string is correctly prefixed for the Vision encoder
            openai_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{item.mimeType};base64,{item.data}",
                    "detail": "high" # Ensures the LLM looks for robotic/technical details
                }
            })
            image = f"data:{item.mimeType};base64,{item.data}"

    # If the MCP server returned nothing, provide a fallback string
    if not openai_content:
        openai_content = [{"type": "text", "text": "Tool executed with no return data."}]

    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": openai_content
    }, "\n".join(texts), image


@sio.event
def connect():
    print("Connected to Flask server!")

@sio.on('client_new')
def handle_new():
    global message_history
    message_history = []

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

    sio.emit("ui_update", { "type": "prompt", "data": "abort" })

    with worker_lock:
        if worker_thread and worker_thread.is_alive():
            return

        # set up stop event for this worker
        worker_stop_event = threading.Event()

        def worker(prompt_text, openai_tools, tools, stop_event):
            try:
                tool_calls = True
                prompt_next = prompt_text
                global message_history
                while (tool_calls) and not stop_event.is_set():
                    # Call the prompt (blocking). In future we
                    # can use stream=True to send partial updates.
                    sio.emit('ui_update',
                            {"type": "response",
                            "data": "Waiting for my brain..."})
                    response, message_history, stats = utils.prompt_with_tools(
                        prompt_next, message_history, tools = openai_tools
                    )
                    print(f"Prompt statistics: {json.dumps(stats, ensure_ascii=False)}")
                    sio.emit('ui_update',
                             {"type": "stats",
                              "data": stats})
                    response_message = response.choices[0].message
                    tool_calls = response_message.tool_calls

                    print(f"Response message content: {response_message.content}")
                    if response_message.content:
                        sio.emit('ui_update',
                                 {"type": "response",
                                  "data": response_message.content})
                        sio.emit('ui_update',
                                 {"type": "response",
                                  "data": f'[{round(stats["elapsed_seconds"],1)}s]'})

                    tool_calls_json = []
                    tool_responses_json = []
                    if tool_calls:
                        for tool_call in tool_calls:
                            if stop_event.is_set():
                                break
                            function_id = tool_call.id
                            function_name = tool_call.function.name
                            function_args = tool_call.function.arguments
                            tool_calls_json.append({
                                'id': function_id,
                                "type": "function",
                                "function": {
                                    "name": function_name,
                                    "arguments": function_args
                                }
                            })
                            print(f"Calling tool {function_name}")
                            sio.emit('ui_update',
                                    {"type": "response",
                                    "data": f"Calling tool {function_name}"})
                            sio.emit('ui_update',
                                    {"type": "response",
                                    "data": f'[{round(stats["elapsed_seconds"],1)}s]'})

                            for tool in tools:
                                if tool[1] == function_name:
                                    rmcp = tool[0]
                                    result = rmcp.call_tool_blocking(function_name, json.loads(function_args))
                                    tool_response, tool_texts, tool_image = mcp_to_openai_multimodal_tool(result, tool_call.id)

                                    tool_responses_json.append(tool_response)
                                    sio.emit('ui_update',
                                             {'type': 'tools_response',
                                              'data': tool_texts})
                                    sio.emit('ui_update',
                                             {'type': 'tools_response',
                                              'data': tool_image})

                        print("Tools finished.")
                        sio.emit('ui_update',
                                {"type": "response",
                                "data": "Tools finished."})
    
                    prompt_next = []
                    # Create the next prompt
                    prompt_next.append({
                        "role": "assistant",
                        "content": response_message.content or "",
                        "tool_calls": tool_calls_json})
                    prompt_next.extend(tool_responses_json)
                    
                # If stop requested, don't emit final result
                if stop_event.is_set():
                    sio.emit("ui_update", { "type": "prompt", "data": "prompt" })
                    return

            except Exception as e:
                print(e)
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

                sio.emit("ui_update", { "type": "prompt", "data": "prompt" })


        #worker_thread = threading.Thread(target=worker, args=(prompt_text, openai_tools, tools, worker_stop_event), daemon=True)
        #worker_thread.start()
        worker_thread = sio.start_background_task(worker, prompt_text, openai_tools, tools, worker_stop_event)

def _connect_one_mcp_server(mcp_server):
    robot_ip = os.getenv('ROBOT_IP', '127.0.0.1')

    if not isinstance(mcp_server, str) or '!' not in mcp_server:
        print('invalid mcp_server entry:', mcp_server)
        return [], []

    kind, rest = mcp_server.split('!', 1)
    rmcp = None
    mcp_tools = None

    if kind == 'ssh':
        # rest is like "user@ip:~/venv/bin/python3:~/test.py"
        user, python_path, script_path = rest.split(':', 2)
        ip = robot_ip
        if '@' in user:
            user, ip = user.split('@', 1)

        rmcp = RemoteMCPManager.RemoteMCPManager()
        rmcp.ssh_connect(user, ip, python_path, script_path)
        mcp_tools = rmcp.get_tools_blocking()

    elif kind == 'sse':
        # rest is like "http://ip:port/test"
        url = rest
        rmcp = RemoteMCPManager.RemoteMCPManager()
        rmcp.sse_connect(url)
        mcp_tools = rmcp.get_tools_blocking()

    elif kind == 'str':
        # rest is like "http://ip:port/mcp"
        url = rest
        rmcp = RemoteMCPManager.RemoteMCPManager()
        rmcp.str_connect(url)
        mcp_tools = rmcp.get_tools_blocking()

    else:
        print('unknown tool kind:', kind)
        return [], []

    local_openai_tools = []
    local_tools = []

    try:
        for tool in mcp_tools.tools:
            print(tool)
            local_openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema,
                    },
                }
            )
            local_tools.append((rmcp, tool.name, tool.description))
    except Exception as e:
        print('failed to parse mcp_tools list:', e)

    return local_openai_tools, local_tools


def connect_mcp_servers():
    # Connect to MCP servers in parallel so one slow server does not block the rest.
    global openai_tools, tools

    max_workers = max(1, min(32, len(toolscfg) or 1))
    collected_openai_tools = []
    collected_tools = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_connect_one_mcp_server, mcp_server): mcp_server for mcp_server in toolscfg}
        for future in as_completed(futures):
            mcp_server = futures[future]
            try:
                local_openai_tools, local_tools = future.result()
                collected_openai_tools.extend(local_openai_tools)
                collected_tools.extend(local_tools)
            except Exception as e:
                print('error processing mcp_server', mcp_server, e)

    openai_tools.extend(collected_openai_tools)
    tools.extend(collected_tools)
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

    connect_mcp_servers()

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
