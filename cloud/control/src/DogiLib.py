import socket
import pickle

# DogiLib.py

class DogiLib:
    def __init__(self):
        # Create a UDP sockets to Dogi
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.connect(('localhost', 5002))

    def control(self, command, args = None):
        if args:
            self.sock.send(pickle.dumps({'name': command, 'args': args}))
        else:
            self.sock.send(pickle.dumps({'name': command}))
