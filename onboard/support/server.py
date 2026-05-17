import asyncio
import argparse
import os
import shlex
import shutil
from asyncio.subprocess import PIPE
from typing import Optional
from bless import (
    BlessServer,
    GATTCharacteristicProperties,
    GATTAttributePermissions
)

# Your custom BME-DOGI-HSN UUID
SERVICE_UUID = "b4e1d091-8571-4b5e-8564-000000000000"
COMMAND_CHAR_UUID = "b4e1d091-8571-4b5e-8564-000000000001"
STATUS_CHAR_UUID = "b4e1d091-8571-4b5e-8564-000000000002"
DEFAULT_PIN = "721135"  
PIN_CODE_FILE = os.path.join(os.path.dirname(__file__), "pincode.txt")
STATUS_WIFI_SCRIPT = os.path.join(os.path.dirname(__file__), "status_wifi.sh")
STATUS_IFACES_SCRIPT = os.path.join(os.path.dirname(__file__), "status_ifaces.sh")
STATUS_ROUTE_SCRIPT = os.path.join(os.path.dirname(__file__), "status_route.sh")
SCRIPT_TIMEOUT_SECONDS = 30.0
COMMAND_SCRIPTS = {
    "WIFISTA": os.path.join(os.path.dirname(__file__), "cmd_wifista.sh"),
    "WIFIAP": os.path.join(os.path.dirname(__file__), "cmd_wifiap.sh"),
    "USEWIFI": os.path.join(os.path.dirname(__file__), "cmd_usewifi.sh"),
    "USE5G": os.path.join(os.path.dirname(__file__), "cmd_use5g.sh"),
    "RESTART": os.path.join(os.path.dirname(__file__), "cmd_restart.sh"),
    "SHUTDOWN": os.path.join(os.path.dirname(__file__), "cmd_shutdown.sh"),
}

def normalize_pin(pin_raw: str) -> str:
    pin = pin_raw.strip()
    if not pin.isdigit():
        raise ValueError("PIN must contain only digits (0-9) for BLE passkey pairing")
    if len(pin) > 6:
        raise ValueError("PIN must be at most 6 digits")
    return pin.zfill(6)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dogi BLE Bless server")
    parser.add_argument(
        "--pin",
        default=DEFAULT_PIN,
        help="BLE pairing PIN/passkey digits only (default is indexes of 'gume')",
    )
    parser.add_argument(
        "--no-pin",
        action="store_true",
        help="Disable PIN requirement for pairing",
    )
    return parser.parse_args()


def write_pin_file(pin_code: str) -> str:
    with open(PIN_CODE_FILE, "w", encoding="utf-8") as pin_file:
        pin_file.write(f"{pin_code}\n")
    os.chmod(PIN_CODE_FILE, 0o600)
    return PIN_CODE_FILE


def read_pin_file() -> str:
    with open(PIN_CODE_FILE, "r", encoding="utf-8") as pin_file:
        return pin_file.read().strip()


async def start_static_pin_agent(pin_file_path: str) -> Optional[asyncio.subprocess.Process]:
    """
    Optionally start an external BlueZ agent that serves a fixed PIN.
    Uses a PIN file with bt-agent's -p option.

    Example BLE_PIN_AGENT_CMD:
    bt-agent -c DisplayOnly -p {pin_file}
    """
    cmd_template = os.getenv(
        "BLE_PIN_AGENT_CMD", "bt-agent -c DisplayOnly -p {pin_file}"
    )
    command = cmd_template.format(pin_file=pin_file_path)
    args = shlex.split(command)
    if not args:
        print("BLE_PIN_AGENT_CMD is empty; skipping static PIN agent")
        return None

    if shutil.which(args[0]) is None:
        print(f"PIN agent tool not found: {args[0]}; continuing without static PIN agent")
        return None

    proc = await asyncio.create_subprocess_exec(*args, stdout=PIPE, stderr=PIPE)
    print(f"Started external PIN agent using: {' '.join(args)}")
    return proc


async def configure_bluez_pairing() -> None:
    """
    Configure BlueZ agent/pairing behavior for headless devices.
    If BLE_STATIC_PIN is set and an external agent is running, bluetoothctl
    still enables pairable/discoverable state and sets default-agent.
    """
    if shutil.which("bluetoothctl") is None:
        print("bluetoothctl not found; continuing without external pairing setup")
        return

    script = "\n".join(
        [
            "power on",
            "discoverable on",
            "pairable on",
            "agent NoInputNoOutput",
            "default-agent",
            "quit",
            "",
        ]
    )

    proc = await asyncio.create_subprocess_exec(
        "bluetoothctl",
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
    )
    stdout, stderr = await proc.communicate(script.encode("utf-8"))

    if proc.returncode != 0:
        print("Failed to configure bluetoothctl agent settings")
        if stderr:
            print(stderr.decode("utf-8", errors="ignore").strip())
    else:
        output = stdout.decode("utf-8", errors="ignore")
        if output.strip():
            print("BlueZ pairing configured via bluetoothctl")


def sanitize_status_text(text: str) -> str:
    cleaned = text.strip()
    while cleaned.endswith("]") or cleaned.endswith('"'):
        cleaned = cleaned[:-1].rstrip()
    return cleaned


def set_status_text(server: BlessServer, text: str) -> None:
    safe_text = sanitize_status_text(text)
    payload = safe_text.encode("utf-8")[:180]
    status_char = server.get_characteristic(STATUS_CHAR_UUID)
    if status_char is None:
        return
    status_char.value = bytearray(payload)
    server.update_value(SERVICE_UUID, STATUS_CHAR_UUID)
    print(f"[DEBUG] Status pushed: {safe_text}")


async def run_command_script(command_name: str) -> str:
    script_path = COMMAND_SCRIPTS.get(command_name)
    if script_path is None:
        return f"ERROR:SCRIPT_NOT_MAPPED:{command_name}"
    if not os.path.exists(script_path):
        print(f"[DEBUG] Script not found for {command_name}: {script_path}")
        return f"{command_name}:ACK"

    proc = await asyncio.create_subprocess_exec(
        script_path,
    )

    try:
        await asyncio.wait_for(proc.wait(), timeout=SCRIPT_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        print(f"[DEBUG] {command_name} script timed out")
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        return f"{command_name}:ACK"

    if proc.returncode != 0:
        print(f"[DEBUG] {command_name} script exited with {proc.returncode}")

    return f"{command_name}:ACK"


async def run_status_script(script_path: str, fallback: str) -> str:
    if not os.path.exists(script_path):
        print(f"[DEBUG] Status script missing: {script_path}")
        return fallback

    proc = await asyncio.create_subprocess_exec(
        script_path,
        stdout=PIPE,
        stderr=PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=SCRIPT_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        print(f"[DEBUG] Status script timeout: {os.path.basename(script_path)}")
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        return fallback

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="ignore").strip()
        if err:
            print(f"[DEBUG] {os.path.basename(script_path)} error: {err}")
        return fallback

    result = stdout.decode("utf-8", errors="ignore").strip()
    return result if result else fallback

async def execute_command_text(command: str, pin_code: Optional[str]) -> tuple[str, bool]:
    # Some BLE clients send fixed-size payloads padded with NUL bytes.
    cmd = command.replace("\x00", "").strip()
    if not cmd:
        return "ERROR:EMPTY_COMMAND", False

    parts = cmd.split()
    head = parts[0].upper()

    if head in COMMAND_SCRIPTS:
        return await run_command_script(head), True

    if head == "PING":
        return "PONG", False
    if head == "AUTH" and len(parts) > 1:
        if pin_code is None:
            return "AUTH:DISABLED", False
        return ("AUTH_OK" if parts[1] == pin_code else "AUTH_FAIL"), False

    if head == "CONNECT":
        return "WELCOME", False

    return f"ERROR:UNKNOWN_COMMAND:{head}", False


async def connection_monitor(server: BlessServer) -> None:
    was_connected = False
    while True:
        try:
            is_connected = await server.is_connected()
        except Exception as exc:
            print(f"[DEBUG] Connection check failed: {exc}")
            await asyncio.sleep(1.0)
            continue

        if is_connected != was_connected:
            event = "connected" if is_connected else "disconnected"
            print(f"[EVENT] Mobile app {event}")
            set_status_text(server, f"EVENT:{event.upper()}")
            was_connected = is_connected

        await asyncio.sleep(1.0)


async def collect_status_messages() -> list[str]:
    wifi, ifaces, route = await asyncio.gather(
        run_status_script(STATUS_WIFI_SCRIPT, "MODE:OFF"),
        run_status_script(STATUS_IFACES_SCRIPT, "wlan0:N/A|wwan0:N/A"),
        run_status_script(STATUS_ROUTE_SCRIPT, "ROUTE:UNKNOWN"),
    )
    return [wifi, ifaces, route]


async def publish_status_once(server: BlessServer) -> None:
    messages = await collect_status_messages()
    for msg in messages:
        set_status_text(server, msg)


async def status_wifi_loop(server: BlessServer) -> None:
    while True:
        wifi = await run_status_script(STATUS_WIFI_SCRIPT, "MODE:OFF")
        set_status_text(server, wifi)
        await asyncio.sleep(3.0)


async def status_ifaces_loop(server: BlessServer) -> None:
    while True:
        ifaces = await run_status_script(STATUS_IFACES_SCRIPT, "wlan0:N/A|wwan0:N/A")
        set_status_text(server, ifaces)
        await asyncio.sleep(3.3)


async def status_route_loop(server: BlessServer) -> None:
    while True:
        route = await run_status_script(STATUS_ROUTE_SCRIPT, "ROUTE:UNKNOWN")
        set_status_text(server, route)
        await asyncio.sleep(3.6)

async def run(pin_code: Optional[str]):
    if pin_code is None:
        print("[BOOT] BLE PIN disabled (no encryption required for pairing)")
        pin_file_path = None
    else:
        pin_file_path = write_pin_file(pin_code)
        file_pin_code = read_pin_file()
        print(f"[BOOT] Using BLE PIN from {PIN_CODE_FILE}: {file_pin_code}")

    pin_agent_proc = None
    if pin_file_path is not None:
        pin_agent_proc = await start_static_pin_agent(pin_file_path)
    await configure_bluez_pairing()

    server = BlessServer(name="Dogi@HSNLab")

    await server.add_new_service(SERVICE_UUID)

    # Define server-level write callback that dispatches to characteristics
    async def process_command(command_text: str) -> None:
        try:
            result, send_heartbeat_now = await execute_command_text(command_text, pin_code)
            print(f"[DEBUG] Command result: {result}")
            set_status_text(server, result)

            if send_heartbeat_now:
                await publish_status_once(server)
        except Exception as exc:
            print(f"[DEBUG] Command processing failed: {exc}")
            set_status_text(server, "ERROR:COMMAND_EXEC")

    def server_write_request(characteristic, value):
        uuid_str = str(characteristic.uuid)
        if uuid_str == COMMAND_CHAR_UUID:
            command_text = value.decode("utf-8", errors="ignore").strip()
            print(f"[DEBUG] Command received raw: {command_text!r}")
            asyncio.create_task(process_command(command_text))
        else:
            print(f"[DEBUG] Write to unknown characteristic: {uuid_str}")

    # Define server-level read callback that dispatches to characteristics
    def server_read_request(characteristic) -> bytearray:
        uuid_str = str(characteristic.uuid)
        if uuid_str == STATUS_CHAR_UUID:
            return characteristic.value
        else:
            return characteristic.value

    # Set server-level callbacks (required by Bless framework)
    server.write_request_func = server_write_request
    server.read_request_func = server_read_request

    # Command input characteristic (mobile app writes commands here).
    cmd_perms = GATTAttributePermissions.readable | GATTAttributePermissions.writeable
    if pin_code is not None:
        cmd_perms |= (GATTAttributePermissions.read_encryption_required |
                      GATTAttributePermissions.write_encryption_required)

    await server.add_new_characteristic(
        SERVICE_UUID,
        COMMAND_CHAR_UUID,
        GATTCharacteristicProperties.read |
        GATTCharacteristicProperties.write,
        bytearray(b""),
        cmd_perms
    )

    # Status output characteristic (server pushes status notifications).
    status_perms = GATTAttributePermissions.readable
    if pin_code is not None:
        status_perms |= GATTAttributePermissions.read_encryption_required

    await server.add_new_characteristic(
        SERVICE_UUID,
        STATUS_CHAR_UUID,
        GATTCharacteristicProperties.read |
        GATTCharacteristicProperties.notify,
        bytearray(b"BOOT"),
        status_perms
    )

    print(f"Starting Dogi Advertise on {SERVICE_UUID}...")
    await server.start()
    set_status_text(server, "STATUS:READY")
    await publish_status_once(server)

    monitor_task = asyncio.create_task(connection_monitor(server))
    wifi_task = asyncio.create_task(status_wifi_loop(server))
    ifaces_task = asyncio.create_task(status_ifaces_loop(server))
    route_task = asyncio.create_task(status_route_loop(server))
    
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        monitor_task.cancel()
        wifi_task.cancel()
        ifaces_task.cancel()
        route_task.cancel()
        await asyncio.gather(
            monitor_task,
            wifi_task,
            ifaces_task,
            route_task,
            return_exceptions=True,
        )
        await server.stop()
        if pin_agent_proc is not None and pin_agent_proc.returncode is None:
            pin_agent_proc.terminate()
            await pin_agent_proc.wait()

if __name__ == "__main__":
    try:
        args = parse_args()
        pin_code: Optional[str] = None
        if not args.no_pin:
            pin_code = normalize_pin(args.pin)
        asyncio.run(run(pin_code))
    except ValueError as exc:
        print(f"Invalid PIN: {exc}")
    except KeyboardInterrupt:
        print("Stopping Dogi Server...")
