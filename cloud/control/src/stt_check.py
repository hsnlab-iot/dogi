import asyncio
import os
import sys

from ably import AblyRealtime
from rich.console import Console

console = Console()

ABLY_API_KEY = (
    os.getenv("ABLY_USER_KEY")
    or os.getenv("ABLY_MASTER_KEY")
    or os.getenv("ABLY_API_KEY")
)

if not ABLY_API_KEY:
    console.print("[bold red]x ERROR: No Ably API key found in environment variables![/bold red]")
    sys.exit(1)

ROOM_ID = os.getenv("ABLY_ROOM_ID", "default-room")
current_active_user = "None (MUTE)"


async def main():
    global current_active_user

    console.print(f"[bold blue]=== STT RECEIVER ONLINE ===[/bold blue]")
    console.print(f"[dim]Listening on Room ID: {ROOM_ID}[/dim]\n")

    try:
        ably = AblyRealtime(ABLY_API_KEY)
        channel = ably.channels.get(f"stt-{ROOM_ID}")
        control_channel = ably.channels.get(f"stt-control-{ROOM_ID}")

        def on_floor_change(message):
            global current_active_user
            new_speaker = message.data.get("activeUser") or "None (MUTE)"
            
            # Only print if floor state actually changed
            if new_speaker != current_active_user:
                current_active_user = new_speaker
                console.print(f"\n[bold yellow]═══ Active Speaker Changed: {current_active_user} ═══[/bold yellow]\n")

        def on_speech_message(message):
            sender = message.data.get("sender")
            text = message.data.get("text", "")
            
            # Only display speech coming from the currently active speaker
            if sender and sender == current_active_user:
                console.print(f"[bold green][{sender}]:[/bold green] {text}")

        await control_channel.subscribe("active-floor", on_floor_change)
        await channel.subscribe("speech", on_speech_message)
        console.print("[green]✓ Subscribed to Ably channels. Waiting for speech...[/green]\n")

    except Exception as e:
        console.print(f"[bold red]x Ably connection error: {e}[/bold red]")
        sys.exit(1)

    # Keep the event loop running indefinitely
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[bold red]Shutting down STT Receiver...[/bold red]")
        sys.exit(0)