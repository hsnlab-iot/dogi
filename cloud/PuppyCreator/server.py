import os
import json
import base64
import subprocess
import time
import re
import threading
import qrcode
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)

# CORS engedélyezése
CORS(app, resources={r"/*": {
    "origins": "*",
    "allow_headers": "*",
    "methods": ["GET", "POST", "OPTIONS"]
}})

UPLOAD_FOLDER = 'dog_profiles'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

public_url = None
url_found_event = threading.Event()

def read_ssh_output(process):
    global public_url
    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if line:
            clean_line = line.strip()
            print(f"[Pinggy SSH] {clean_line}")
            
            # Kizárjuk a dashboard.pinggy.io-t
            match = re.search(r'https://[a-zA-Z0-9\-]+\.(?:run\.pinggy-free\.link|free\.pinggy\.net|a\.pinggy\.link|a\.pinggy\.io)', clean_line)
            
            if match and not public_url:
                found_url = match.group(0)
                if "dashboard" not in found_url:
                    public_url = found_url
                    url_found_event.set()

def start_pinggy_tunnel(port=5000):
    print("= SSH Alagút indítása a Pinggy felé...")
    
    cmd = [
        "ssh",
        "-p", "443",
        "-R0:localhost:5000",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ServerAliveInterval=30",
        "a.pinggy.io",
        "p:5000+http"
    ]
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
            bufsize=1
        )
    except Exception as e:
        print(f" HIBA az SSH indításakor: {e}")
        return None, None

    output_thread = threading.Thread(target=read_ssh_output, args=(process,), daemon=True)
    output_thread.start()

    print(" Várakozás a Pinggy URL-re...")
    got_url = url_found_event.wait(timeout=10)
    return process, public_url if got_url else None

def print_qr_code(url):
    qr = qrcode.QRCode(version=1, box_size=1, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    
    print("\n" + "="*60)
    print(" PINGGY ALAGÚT AKTÍV!")
    print(f" Cél URL a telefonnak: {url}")
    print("="*60 + "\n")
    qr.print_tty()
    print("\n" + "="*60 + "\n")

@app.before_request
def log_request_info():
    if request.method != 'OPTIONS':
        print(f"\n [ÚJ KÉRÉS] {request.method} -> {request.url}")

@app.route('/upload', methods=['GET', 'POST', 'OPTIONS'])
def upload_profile():
    # Preflight (OPTIONS)
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = '*'
        return response, 200

    # GET metódus: amikor a felhasználó megnyitja a böngészőben az alagút nyitásakor
    if request.method == 'GET':
        return """
        <html>
            <head><title>Alagút Aktív</title></head>
            <body style="font-family:sans-serif; text-align:center; padding-top:50px;">
                <h1 style="color:green;"> Az alagút sikeresen aktiválva!</h1>
                <p>Most már visszatérhetsz az alkalmazásba, és elküldheted a profil adatokat.</p>
                <p><small>(Ezt az ablakot bezárhatod)</small></p>
            </body>
        </html>
        """, 200

    # POST adatok mentése
    try:
        json_str = request.form.get('json_data')
        if not json_str:
            return jsonify({'status': 'error', 'message': 'Hiányzó json_data'}), 400
        
        data = json.loads(json_str)
        dog_name = data.get('name', 'Bodri').strip()
        safe_folder_name = "".join([c for c in dog_name if c.isalnum() or c in (' ', '_', '-')]).rstrip() or "Bodri"

        target_dir = os.path.join(UPLOAD_FOLDER, safe_folder_name)
        os.makedirs(target_dir, exist_ok=True)

        text_data = {
            'name': data.get('name', ''),
            'story': data.get('story', ''),
            'traits': data.get('traits', '')
        }
        with open(os.path.join(target_dir, 'profile_data.json'), 'w', encoding='utf-8') as f:
            json.dump(text_data, f, ensure_ascii=False, indent=4)

        photo_base64 = data.get('photo')
        if photo_base64:
            if ',' in photo_base64:
                photo_base64 = photo_base64.split(',')[1]
            image_bytes = base64.b64decode(photo_base64)
            with open(os.path.join(target_dir, 'photo.jpg'), 'wb') as f:
                f.write(image_bytes)

        if 'audio' in request.files:
            audio_file = request.files['audio']
            if audio_file.filename != '':
                audio_file.save(os.path.join(target_dir, 'voice.webm'))

        print(f" SIKERES MENTÉS: {target_dir}")
        res = jsonify({'status': 'success', 'message': f'Profil elmentve: {safe_folder_name}'})
        res.headers['Access-Control-Allow-Origin'] = '*'
        return res, 200

    except Exception as e:
        print(f" SZERVER HIBA: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    PORT = 5000
    pinggy_proc, target_url = start_pinggy_tunnel(port=PORT)

    if target_url:
        upload_endpoint = f"{target_url}/upload"
        print_qr_code(upload_endpoint)
    else:
        print("\n FIGYELEM: Nem sikerült lekérni a Pinggy URL-t.")

    print(f"= Flask webszerver indítása a 0.0.0.0:{PORT} porton...")
    try:
        app.run(host='0.0.0.0', port=PORT, debug=False)
    finally:
        if pinggy_proc:
            pinggy_proc.terminate()
