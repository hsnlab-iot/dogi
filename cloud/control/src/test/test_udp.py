import time
import socket
import pickle

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.connect(('localhost', 5002))

sock.send(pickle.dumps({'name': 'reset'}))
time.sleep(1)
sock.send(pickle.dumps({'name': 'motor', 'args': (13, 31)}))
sock.send(pickle.dumps({'name': 'motor', 'args': (43, 31)}))
