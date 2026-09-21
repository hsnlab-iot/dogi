import os
import re
import socket
import subprocess
import threading
import time

from flask import Flask, send_from_directory
import qrcode

ROOM_ID = os.getenv("ABLY_ROOM_ID", "default-room")
ABLY_MASTER_KEY = os.getenv("ABLY_MASTER_KEY", "")

# --- RESOLVE ABSOLUTE PATHS ---
# This ensures Flask finds the folder even if run from different directories.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Map the Python-side folder name
STATIC_STT_DIR = os.path.join(BASE_DIR, "static-stt")

app = Flask(
    __name__,
    static_folder=STATIC_STT_DIR,
    static_url_path="/static"
)

def get_local_ip():
    """Returns the local LAN IP address of the server host machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


# --- FLASK ROUTES & SERVINGS ---

@app.route("/")
@app.route("/master.html")
def master_page():
    """Serves static master.html directly without embedding sensitive keys."""
    return app.send_static_file("master.html")

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory(app.static_folder, "manifest.json", mimetype="application/manifest+json")

@app.route("/sw.js")
def serve_service_worker():
    """
    Serves the Service Worker from the static directory with the proper MIME type
    and Service-Worker-Allowed header to give it full root-scope authority.
    """
    response = send_from_directory(
        app.static_folder, 
        "sw.js", 
        mimetype="application/javascript"
    )
    # Allows the service worker to control requests across the entire site (/)
    response.headers["Service-Worker-Allowed"] = "/"
    return response

# --- ASCII QR CODE PRINTING ---
def print_ascii_qr(title, content, redact=False):
    """Generates and displays an ASCII QR code directly in terminal/tmux."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=2,
    )
    qr.add_data(content)
    qr.make(fit=True)

    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)
    if redact:
        preview = content[:8] + "..." if len(content) > 8 else "[EMPTY]"
        print(f"Secret Key Preview: {preview} [REDACTED FOR SECURITY]\n")
    else:
        print(f"URL: {content}\n")

    qr.print_ascii(invert=True)
    print("=" * 60 + "\n")


def print_key_qr():
    """Prints the secret ABLY_MASTER_KEY as an ASCII QR code to tmux."""
    if ABLY_MASTER_KEY:
        print_ascii_qr("1. SCAN WITH APP CAMERA: ABLY MASTER KEY", ABLY_MASTER_KEY, redact=True)
    else:
        print("\n[WARNING] 'ABLY_MASTER_KEY' environment variable is missing or empty!\n")


# --- PINGGY SSH TUNNEL BACKGROUND WORKER ---

def pinggy_tunnel_worker(server_port):
    """Background worker thread to establish Pinggy tunnel using the dynamically assigned port."""
    path_param = f"master.html?room={ROOM_ID}"

    while True:
        print(f"[PINGGY] Initiating SSH Tunnel for Master App (Forwarding Port {server_port})...")
        # Pass the header key AND value explicitly
        cmd = [
            "ssh",
            "-T",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ServerAliveInterval=30",
            "-p", "443",
            f"-R0:localhost:{server_port}",
            f"{path_param}@a.pinggy.io",
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            os.set_blocking(proc.stdout.fileno(), False)
        except Exception as e:
            print(f"[PINGGY] Failed to launch SSH process: {e}")
            time.sleep(10)
            continue

        extracted_url = None
        start_time = time.time()
        buffer = ""

        # Non-blocking read to capture generated Pinggy URL
        while time.time() - start_time < 15:
            try:
                chunk = proc.stdout.read()
                if chunk:
                    buffer += chunk
                    match = re.search(
                        r"https://[a-zA-Z0-9-]+\.(run\.pinggy-free\.link|free\.pinggy\.net|pinggy\.link)",
                        buffer,
                    )
                    if match:
                        extracted_url = match.group(0) + f"/{path_param}"
                        break
            except (IOError, TypeError):
                pass
            time.sleep(0.3)

        if extracted_url:
            # Display App Download URL QR Code (No secret keys embedded)
            print_ascii_qr("2. SCAN TO DOWNLOAD MASTER PWA APP (NO SECRET KEYS)", extracted_url)

            # Display Secret Master Key QR Code for inside-app scanning
            print_key_qr()

            while proc.poll() is None:
                time.sleep(5)

            print("[PINGGY] Tunnel disconnected. Reconnecting in 5 seconds...")
        else:
            print("[PINGGY] Timeout / Failed to extract URL from Pinggy output.")
            proc.kill()

        time.sleep(5)


# --- MAIN ENTRYPOINT WITH DYNAMIC PORT BINDING ---

if __name__ == "__main__":
    # Create socket and bind to port 0 to obtain an OS-assigned dynamic port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("0.0.0.0", 0))
    dynamic_port = sock.getsockname()[1]
    sock.close()  # Close temporary socket so Flask can bind to this port

    local_ip = get_local_ip()
    local_url = f"http://{local_ip}:{dynamic_port}/master.html?room={ROOM_ID}"

    print("\n" + "#" * 60)
    print(f" STT MASTER SERVER INITIALIZING")
    print(f" Assigned Dynamic Port: {dynamic_port}")
    print(f" Room ID               : {ROOM_ID}")
    print(f" Local LAN URL         : {local_url}")
    print("#" * 60 + "\n")

    # Start Pinggy tunnel thread passing the dynamic port
    tunnel_thread = threading.Thread(target=pinggy_tunnel_worker, args=(dynamic_port,), daemon=True)
    tunnel_thread.start()

    # Start Flask Web Server on the dynamic port
    app.run(host="0.0.0.0", port=dynamic_port)