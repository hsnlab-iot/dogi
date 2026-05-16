import pickle

import config


def dogy_control(command, args=None):
    sock = config.get_control_socket()
    if args:
        sock.send(pickle.dumps({'name': command, 'args': args}))
    else:
        sock.send(pickle.dumps({'name': command}))


def dogy_look(r, p, y):
    dogy_control('attitude', (['r', 'p', 'y'], [r, p, y]))


def dogy_reset():
    dogy_control('reset')
