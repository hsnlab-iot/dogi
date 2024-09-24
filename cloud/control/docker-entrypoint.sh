#!/bin/bash -x

tmux new-session -d -s supervisord "/root/.local/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf"
tmux new-session -d -s video "python3 /root/zmq_videopub.py ; sleep inf"

# Wait for the serial port to be available
while [ ! -e /dev/ttyAMA0 ]; do
    sleep 1
done

tmux new-session -d -s data "python3 /root/DOGZILLAProxyServer.py ; sleep inf"

# Wait for UDP port 5001 to start listening
while ! netstat -tuln | grep -q ":5002 "; do
    sleep 1
done
tmux new-session -d -s webvideo "cd /root && source .flask/bin/activate && python3 webvideo.py ; sleep inf"
tmux new-session -d -s webjoy "cd /root && source .flask/bin/activate && python3 webjoy.py ; sleep inf"

tail -f /dev/null