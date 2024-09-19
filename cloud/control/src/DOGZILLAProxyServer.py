from DOGZILLALib.DOGZILLALib import DOGZILLALib as dog
import time
import socket
import pickle

def main():

    # Create control interface
    dogControl = dog.DOGZILLA("/dev/ttyAMA0")
    time.sleep(1)

    # Create a UDP socket
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Bind the socket to a specific address and port
    udp_socket.bind(("localhost", 5002))

    addr_lock = None
    addr_lock_time = None

    while True:
        # Receive data from the socket
        data, addr = udp_socket.recvfrom(1024)
        addr_str = addr[0] + ":" + str(addr[1])
        
        if addr_lock_time is not None and time.time() - addr_lock_time > 5:
            addr_lock = None

        if addr_lock is None:
            addr_lock = addr_str
            addr_lock_time = time.time()
            print("Locking to", addr_lock)
        elif addr_str != addr_lock:
            print("Ignoring data from", addr_str)
            continue

        try:
            # Process the received command
            command = pickle.loads(data)
            command_name = command.get("name")
            command_args = command.get("args")

            if command_name in dir(dogControl):
                func = getattr(dogControl, command_name)
                if command_args is None:
                    func()
                else:
                    func(*command_args)
            else:
                print("Unknown command:", command_name)

        except Exception as e:
            print("Error processing command:", str(e))

if __name__ == "__main__":
    main()