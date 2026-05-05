import cv2
import numpy as np
import zmq
import time
import socket
import pickle
import threading
import random
from io import BytesIO
import os
import glob

import utils
import config

PORT = 5056

DEBUG_mode = os.getenv('DEBUG', '0') == '1'

config.init()

# Create a UDP sockets to web page server
sock_web = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock_web.connect(('localhost', PORT))

text = {
    'en': "Give me a prompt, and I will do it!",
    'hu': "Adj egy utasítást, és én végrehajtom!"
}
xtext = utils.select_text(text, config.get_ui_language(), True)
print(xtext)
wav, d = utils.tts_wav(xtext, config.get_ui_language() + "_intro_keresd")
utils.play_wav(wav)
time.sleep(d)

utils.dogy_reset()

while True:
    time.sleep(1)

