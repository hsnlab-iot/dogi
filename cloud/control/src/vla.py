import os
import time
import config
import socketio
from loguru import logger

logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    level="DEBUG",
    format="<green>{time:HH:mm:ss}</green> <level>{message}</level>",
)

PORT = 5061
sio = socketio.Client()

config.init()


@sio.event
def connect():
    logger.info("VLA connected to Flask server!")


@sio.on('client_new')
def handle_new():
    pass


@sio.on('client_speak')
def handle_speak(data):
    pass


@sio.on('client_abort')
def handle_abort(data=None):
    pass


@sio.on('client_prompt')
def handle_prompt(data):
    pass


if __name__ == '__main__':
    sio.connect(f'http://localhost:{PORT}', socketio_path='/socket.io/')
    sio.emit('ui_update', {'type': 'prompt', 'data': 'prompt'})
    sio.wait()
