import pickle
import socket
import time


class CommandProxy:
    """Keep one local command sender; Stop always works and releases ownership."""

    def __init__(self, dog_control):
        self.dog_control = dog_control
        self.owner = None
        self.owner_since = 0

    def dispatch(self, command, address):
        if not isinstance(command, dict):
            raise ValueError("Command must be a dictionary")
        name, args = command.get("name"), command.get("args")
        if not isinstance(name, str) or name.startswith("_"):
            raise ValueError("Invalid command name")
        if args is not None and not isinstance(args, (list, tuple)):
            raise ValueError("Command args must be a list or tuple")
        if name not in dir(self.dog_control):
            raise ValueError(f"Unknown command: {name}")
        now = time.monotonic()
        if name != "stop":
            if self.owner is not None and now - self.owner_since > 5:
                self.owner = None
            if self.owner is None:
                self.owner, self.owner_since = address, now
                print("Locking to", address)
            elif address != self.owner:
                print("Ignoring data from", address)
                return False
        function = getattr(self.dog_control, name)
        function(*(args or ()))
        if name == "stop":
            self.owner = None
        return True


def main():
    # Web API version; the serial port argument is ignored.
    from DOGZILLALib.DOGZILLALib import DOGZILLALibClient as dog

    proxy = CommandProxy(dog.DOGZILLA("/dev/ttyAMA0"))
    time.sleep(1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.bind(("localhost", 5002))
        while True:
            data, address = udp_socket.recvfrom(1024)
            try:
                # Existing protocol, confined to local processes in this container.
                proxy.dispatch(pickle.loads(data), address)
            except Exception as exc:
                print("Error processing command:", str(exc))


if __name__ == "__main__":
    main()
