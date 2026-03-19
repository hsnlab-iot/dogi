#!/bin/bash -x

export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

tmux new-session -d -s supervisord "/root/.local/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf"
tmux new-session -d -s video "python3 /app/zmq_videopub.py ; sleep inf"

# Wait for the serial port to be available
while [ ! -e /dev/ttyAMA0 ]; do
    sleep 1
done

tmux new-session -d -s data "python3 /app/DOGZILLAProxyServer.py ; sleep inf"

# Wait for UDP port 5002 to start listening
while ! netstat -tuln | grep -q ":5002 "; do
    sleep 1
done
tmux new-session -d -s webvideo "cd /app && source /opt/venv/bin/activate && python3 web_video.py ; sleep inf"
#tmux new-session -d -s webjoy "cd /app && source /opt/venv/bin/activate && python3 web_joy.py ; sleep inf"
tmux new-session -d -s webjoy "cd /app && source /opt/venv/bin/activate && python3 web_joy.py ; sleep inf"
#tmux new-session -d -s webvoice "cd /app && source /opt/venv/bin/activate && python3 web_voice.py ; sleep inf"
tmux new-session -d -s webvoice "cd /app && source /opt/venv/bin/activate && python3 web_voice.py ; sleep inf"
tmux new-session -d -s webkeresd "cd /app && source /opt/venv/bin/activate && python3 web_keresd.py ; sleep inf"
tmux new-session -d -s webkovesd "cd /app && source /opt/venv/bin/activate && python3 web_kovesd.py ; sleep inf"
tmux new-session -d -s webmutasd "cd /app && source /opt/venv/bin/activate && python3 web_mutasd.py ; sleep inf"
tmux new-session -d -s webmain "cd /app && source /opt/venv/bin/activate && python3 web_main.py ; sleep inf"

tail -f /dev/null
