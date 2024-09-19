#!/bin/bash -x

tmux new-session -d -s video "python3 /root/zmq_videopub.py && sleep inf"
tmux new-session -d -s data "python3 /root/DOGZILLAProxyServer.py && sleep inf"

tail -f /dev/null