import asyncio
import argparse
import os
import base64
import json
import sys
from datetime import datetime
from typing import Optional
from bless import (
    BlessServer,
    GATTCharacteristicProperties,
    GATTAttributePermissions
)

from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SERVICE_UUID = "b4e1d091-8571-4b5e-8564-000000000000"
COMMAND_CHAR_UUID = "b4e1d091-8571-4b5e-8564-000000000001"
STATUS_CHAR_UUID = "b4e1d091-8571-4b5e-8564-000000000002"

DEFAULT_PIN = "721135"
PIN_CODE_FILE = os.path.join(os.path.dirname(__file__), "pincode.txt")
STATUS_WIFI_SCRIPT = os.path.join(os.path.dirname(__file__), "status_wifi.sh")
STATUS_IFACES_SCRIPT = os.path.join(os.path.dirname(__file__), "status_ifaces.sh")
STATUS_ROUTE_SCRIPT = os.path.join(os.path.dirname(__file__), "status_route.sh")
SCRIPT_TIMEOUT_SECONDS = 5.0

COMMAND_SCRIPTS = {
    "WSTA": os.path.join(os.path.dirname(__file__), "cmd_wifista.sh"),
    "WAP": os.path.join(os.path.dirname(__file__), "cmd_wifiap.sh"),
    "USEWIFI": os.path.join(os.path.dirname(__file__), "cmd_usewifi.sh"),
    "USE5G": os.path.join(os.path.dirname(__file__), "cmd_use5g.sh"),
    "RESTART": os.path.join(os.path.dirname(__file__), "cmd_restart.sh"),
    "SHUTDOWN": os.path.join(os.path.dirname(__file__), "cmd_shutdown.sh"),
}

def log(tag: str, msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{tag}] {msg}", flush=True)

def get_shared_secret_pin() -> str:
    if os.path.exists(PIN_CODE_FILE):
        try:
            with open(PIN_CODE_FILE, "r", encoding="utf-8") as f:
                pin = f.read().strip()
                if pin:
                    return pin
        except Exception as e:
            log("BOOT-ERR", f"Error reading pin file: {e}")
    return os.getenv("BLE_PIN", DEFAULT_PIN)

class NoisePSKSession:
    def __init__(self, psk_passphrase: str):
        self.psk_bytes = psk_passphrase.encode("utf-8")
        self.private_key = None
        self.session_key = None

    def generate_ephemeral_key(self) -> str:
        self.private_key = x25519.X25519PrivateKey.generate()
        public_bytes = self.private_key.public_key().public_bytes_raw()
        return base64.b64encode(public_bytes).decode('utf-8')

    def derive_session_key(self, client_pub_b64: str):
        client_pub_bytes = base64.b64decode(client_pub_b64)
        client_public_key = x25519.X25519PublicKey.from_public_bytes(client_pub_bytes)
        dh_secret = self.private_key.exchange(client_public_key)

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.psk_bytes,
            info=b"noise-psk-ble-v1",
        )
        self.session_key = hkdf.derive(dh_secret)

    def decrypt(self, nonce_b64: str, ciphertext_b64: str) -> str:
        if not self.session_key:
            raise ValueError("No active session key")
        aesgcm = AESGCM(self.session_key)
        nonce = base64.b64decode(nonce_b64)
        ciphertext = base64.b64decode(ciphertext_b64)
        decrypted = aesgcm.decrypt(nonce, ciphertext, None)
        return decrypted.decode('utf-8')

    def encrypt(self, plaintext: str) -> str:
        if not self.session_key:
            return plaintext
        aesgcm = AESGCM(self.session_key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
        payload = {
            "nonce": base64.b64encode(nonce).decode('utf-8'),
            "ct": base64.b64encode(ciphertext).decode('utf-8')
        }
        return "ENC:" + json.dumps(payload)

psk_secret = get_shared_secret_pin()
session = NoisePSKSession(psk_secret)

async def set_status_text(server: BlessServer, text: str) -> None:
    if not text:
        return

    if session.session_key and not text.startswith("KEYEX_RESP:"):
        payload_str = session.encrypt(text)
    else:
        payload_str = text

    payload = payload_str.encode("utf-8")

    try:
        status_char = server.get_characteristic(STATUS_CHAR_UUID)
        if status_char is not None:
            status_char.value = bytearray(payload)
            server.update_value(SERVICE_UUID, STATUS_CHAR_UUID)
    except Exception as e:
        log("STATUS-ERR", f"Failed to send status update: {e}")

async def run_command_script(command_name: str) -> str:
    script_path = COMMAND_SCRIPTS.get(command_name)
    if not script_path or not os.path.exists(script_path):
        log("CMD", f"Script not found for {command_name}, sending ACK")
        return f"{command_name}:ACK"
    try:
        log("EXEC", f"Executing script for command: {command_name} ({script_path})")
        proc = await asyncio.create_subprocess_exec(script_path)
        await asyncio.wait_for(proc.wait(), timeout=SCRIPT_TIMEOUT_SECONDS)
        log("EXEC", f"Script finished for {command_name}")
    except Exception as e:
        log("EXEC-ERR", f"Error executing {command_name}: {e}")
    return f"{command_name}:ACK"

async def run_status_script(script_path: str, fallback: str) -> str:
    if not os.path.exists(script_path):
        return fallback
    try:
        proc = await asyncio.create_subprocess_exec(
            script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=SCRIPT_TIMEOUT_SECONDS)
        res = stdout.decode("utf-8", errors="ignore").strip()
        return res if res else fallback
    except Exception:
        return fallback

async def execute_command_text(raw_input: str) -> str:
    cmd_str = raw_input.replace("\x00", "").strip()

    if cmd_str.startswith("KEYEX:"):
        log("HANDSHAKE", "Received KEYEX from client. Processing Noise-PSK exchange...")
        client_pub_b64 = cmd_str.split("KEYEX:")[1]
        server_pub_b64 = session.generate_ephemeral_key()
        session.derive_session_key(client_pub_b64)
        log("HANDSHAKE", "Key exchange successful! Encrypted channel ready.")
        return f"KEYEX_RESP:{server_pub_b64}"

    if cmd_str.startswith("ENC:"):
        try:
            data = json.loads(cmd_str[4:])
            cmd_str = session.decrypt(data["nonce"], data["ct"])
            log("RECV-ENC", f"Decrypted Command: '{cmd_str}'")
        except Exception as e:
            log("AUTH-ERR", f"Decryption failed: {e}")
            return "ERROR:AUTH_FAILED"

    parts = cmd_str.split()
    head = parts[0].upper() if parts else ""

    if head in COMMAND_SCRIPTS:
        return await run_command_script(head)
    if head == "PING":
        return "PONG"
    if head == "CONNECT":
        log("CLIENT", "Client connected and sent CONNECT request.")
        return "WELCOME"

    return f"ERROR:UNKNOWN:{head}"

# Telemetria Ciklus vizuális visszajelzéssel
async def status_polling_loop(server: BlessServer):
    tick = 0
    while True:
        try:
            if session.session_key:
                # Szkriptek futtatása a valós adatok lekéréséhez
                wifi = await run_status_script(STATUS_WIFI_SCRIPT, "MODE:STA")
                ifaces = await run_status_script(STATUS_IFACES_SCRIPT, "wlan0:192.168.1.10|wwan0:N/A")
                route = await run_status_script(STATUS_ROUTE_SCRIPT, "ROUTE:WiFi")

                # Tiszta, egységes formátum összeállítása Pipe (|) elválasztóval
                combined_status = f"{ifaces} | {wifi} | {route}"
                await set_status_text(server, combined_status)

                # Periodikus konzol visszajelzés
                tick += 1
                if tick % 5 == 0:
                    log("POLL", f"Broadcasting Telemetry: {combined_status}")
            else:
                tick += 1
                if tick % 10 == 0:
                    log("IDLE", "Waiting for client connection / handshake...")
        except Exception as e:
            log("POLL-ERR", f"{e}")

        await asyncio.sleep(3.0)

async def run():
    print("=" * 60)
    print("           DOGI CONTROLLER BLE SERVER (Noise-PSK)          ")
    print("=" * 60)
    log("BOOT", f"Loaded PSK Passphrase: {'*' * len(psk_secret)}")

    server = BlessServer(name="Dogi@HSNLab")
    await server.add_new_service(SERVICE_UUID)

    async def process_command(command_text: str) -> None:
        result = await execute_command_text(command_text)
        await set_status_text(server, result)

    def server_write_request(characteristic, value):
        if str(characteristic.uuid) == COMMAND_CHAR_UUID:
            command_text = value.decode("utf-8", errors="ignore").strip()
            asyncio.create_task(process_command(command_text))

    def server_read_request(characteristic) -> bytearray:
        return characteristic.value

    server.write_request_func = server_write_request
    server.read_request_func = server_read_request

    open_perms = GATTAttributePermissions.readable | GATTAttributePermissions.writeable

    await server.add_new_characteristic(
        SERVICE_UUID, COMMAND_CHAR_UUID,
        GATTCharacteristicProperties.read | GATTCharacteristicProperties.write,
        bytearray(b""), open_perms
    )

    await server.add_new_characteristic(
        SERVICE_UUID, STATUS_CHAR_UUID,
        GATTCharacteristicProperties.read | GATTCharacteristicProperties.notify,
        bytearray(b"BOOT"), open_perms
    )

    log("BLE", "Starting Open BLE Server...")
    await server.start()
    log("BLE", "Server is RUNNING and advertising as 'Dogi@HSNLab'")
    print("-" * 60)

    # Telemetriai ciklus indítása
    asyncio.create_task(status_polling_loop(server))

    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n")
        log("SYS", "Server stopped by user (Ctrl+C). Exiting...")
        sys.exit(0)