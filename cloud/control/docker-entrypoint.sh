#!/bin/bash -x

export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONUTF8=1
export PYTHONIOENCODING=UTF-8

tmux new-session -d -s supervisord "/root/.local/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf"
tmux new-session -d -s video "python3 /app/zmq_videopub.py ; sleep inf"
tmux new-session -d -s streamer "cd /app && source /opt/venv/bin/activate && python3 /app/streamer_client.py ; sleep inf"
tmux new-session -d -s ollama_exporter "cd /app && python3 ollama_exporter.py --ollama-url http://10.6.6.20:11434 --log-level DEBUG ; sleep inf"

tmux new-session -d -s data "python3 /app/DOGZILLAProxyServer.py ; sleep inf"

# Wait for UDP port 5002 to start listening for the DOGZILLAProxyServer
while ! netstat -tuln | grep -q ":5002 "; do
    sleep 1
done

tmux new-session -d -s webmain "cd /app && source /opt/venv/bin/activate && python3 web_main.py ; sleep inf"
tmux new-session -d -s webvideo "cd /app && source /opt/venv/bin/activate && python3 web_video.py ; sleep inf"
tmux new-session -d -s webvoice "cd /app && source /opt/venv/bin/activate && python3 web_voice.py ; sleep inf"

tmux new-session -d -s websystem "cd /app && source /opt/venv/bin/activate && python3 web_system.py ; sleep inf"
tmux new-session -d -s webkeresd "cd /app && source /opt/venv/bin/activate && python3 web_keresd.py ; sleep inf"
tmux new-session -d -s webkovesd "cd /app && source /opt/venv/bin/activate && python3 web_kovesd.py ; sleep inf"
tmux new-session -d -s webmutasd "cd /app && source /opt/venv/bin/activate && python3 web_mutasd.py ; sleep inf"
tmux new-session -d -s webprompt "cd /app && source /opt/venv/bin/activate && python3 web_prompt.py ; sleep inf"
tmux new-session -d -s webpupality "cd /app && source /opt/venv/bin/activate && python3 web_pupality.py ; sleep inf"

tail -f /dev/null
