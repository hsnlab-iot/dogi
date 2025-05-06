import cv2
import numpy as np
import zmq
import time
import socket
import pickle
import threading
import ollama
import random
from io import BytesIO
import os

import utils

PORT = 5053

MAXPITCH = 20
MAXYAW = 16

# Create a UDP sockets to web page server
sock_web = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock_web.connect(('localhost', PORT))

model = os.environ.get('MODEL', 'llama3.1')
visual_model = os.environ.get('VISUAL_MODEL', 'llava:13b')

# Subscribe to video
zmqcontext = zmq.Context()
subscriber = zmqcontext.socket(zmq.SUB)
subscriber.setsockopt(zmq.CONFLATE, 1)
subscriber.setsockopt_string(zmq.SUBSCRIBE, '')  # Subscribe to all topics
subscriber.connect("ipc:///tmp/video_frames_c.ipc")  # IPC socket address

publisher = zmqcontext.socket(zmq.PUB)
publisher.bind("ipc:///tmp/video_frames_keresd.ipc")

text = "Ready or not, here I come! Watch out, I'm starting to look!"
if utils.get_language() == 'Hungarian':
    text = "Aki bújt, aki nem, indulok. Figyelj, keresni kezdek. "
else:
    text = utils.translate(text)
wav, d = utils.tts_wav(text)
utils.play_wav(wav)
time.sleep(d)

def move_forward():
    utils.dogy_look(0, 0, 0) # Look straight
    time.sleep(1)
    utils.dogy_control('forward', (5, ))
    time.sleep(3)
    utils.dogy_control('stop')

def turn_left():
    utils.dogy_look(0, 0, 0) # Look straight
    time.sleep(1)
    utils.dogy_control('turn', (5, ))
    time.sleep(3)
    utils.dogy_control('stop')

def turn_right():
    utils.dogy_look(0, 0, 0) # Look straight
    time.sleep(1)
    utils.dogy_control('turn', (-5, ))
    time.sleep(3)
    utils.dogy_control('stop')

def look_left_right():
    threading.current_thread().stopped = False
    while not threading.current_thread().stopped:
        utils.dogy_look(0, MAXPITCH, -MAXYAW) # Look left
        time.sleep(1.5)
        if threading.current_thread().stopped:
            break
        utils.dogy_look(0, MAXPITCH, MAXYAW) # Lookright
        time.sleep(1.5)
        if threading.current_thread().stopped:
            break
        utils.dogy_look(0, MAXPITCH, 0) # Look front
        time.sleep(1.5)

    utils.dogy_look(0, MAXPITCH, 0) # Look front

# Function to process the frame
def take_frame():
    
    frame_bytes = None
    try:
        frame_bytes = subscriber.recv()
    except zmq.error.Again:
        pass  # No frame received, continue processing

    if frame_bytes is None:
        return None

    publisher.send(frame_bytes)

    width = 640
    height = 480
    img_array = np.frombuffer(frame_bytes, dtype=np.uint8)
    img_array = img_array.reshape((height, width, 3))
    img_array = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
    return img_array

ollama_client = utils.get_ollama_client()

while True:

    utils.dogy_reset()
    time.sleep(1)

    utils.dogy_look(0, MAXPITCH, 0) # Look front
    time.sleep(1.5)
    front_pic = take_frame()
    
    # Save front_pic into the current folder in jpeg format
    filename = "front_pic_{}.jpeg".format(time.time())
    cv2.imwrite(filename, front_pic)

    # Display the picture
    cv2.imshow("Front", front_pic)
    cv2.waitKey(1)

    # Start the looking thread
    thread = threading.Thread(target=look_left_right)
    thread.start()

    is_success, img_buffer = cv2.imencode(".jpg", front_pic)
    print("Ask ollama about obstacles")
    start_time = time.time()

    obstacles = None
    ball_found = False

    try:
        whatisit = ollama_client.generate(model=visual_model, 
            prompt='This is a liveview capture taken by a front camera of a robot dog.' \
                'The robot dog is looking straight ahead and a bit down.' \
                'Make a short description, briefly what is on the picture!' \
                'Focus on the near objects, ignore far away objects!' \
                'Try to describe these objects relative to the center of the picture!'  \
                ,
            images=[img_buffer.tobytes()],
            stream=False)

        text = whatisit['response'].strip()
        print(f"Description: {text}")
        sock_web.send(pickle.dumps({'action': 'entext', 'text': text}))
        print("Ask translation" )
        xtext = utils.translate(text)
        print("Translation: ", xtext)
        sock_web.send(pickle.dumps({'action': 'xtext', 'text': xtext}))
        print("TTS")
        wav, d = utils.tts_wav(xtext)
        utils.play_wav(wav)
        time.sleep(d)

        ball = ollama_client.generate(model=model, 
            prompt='Answer with a single word, YES or NO! Based on the following description, are there any balls in this description: ' + 
                whatisit['response'].strip() \
                ,
            stream=False)

        print("Ball: ", ball['response'].strip())

        if ball['response'].strip() in ['YES', 'Yes', 'YES!']:
            text = "I found a ball." # // "Hurrá, megtaláltam a labdát. ")
            xtext = utils.translate(text)
            wav, d = utils.tts_wav(xtext)
            utils.play_wav(wav)
            time.sleep(d)

            ball_found = True
            ball_place = ollama_client.generate(model=visual_model, 
                prompt='This is a liveview capture taken by a front camera of a robot dog.' \
                    'Describe where you see the ball on the picture, and how does the ball look like' \
                    ,
                images=[img_buffer.tobytes()],
                stream=False)

            text = ball_place['response'].strip()
            print(f"Ball place: {text}")
            sock_web.send(pickle.dumps({'action': 'entext', 'text': text}))
            print("Ask translation" )
            xtext = utils.translate(text)
            print("Translation: ", xtext)
            sock_web.send(pickle.dumps({'action': 'xtext', 'text': xtext}))
            print("TTS")
            wav, d = utils.tts_wav(xtext)
            utils.play_wav(wav)
            time.sleep(d)

            print("Ball detected, stopping")

            # Stop the thread
            thread.stopped = True
            thread.join()
            break

        obstacles = ollama_client.generate(model=model,
            prompt='Answer with a word, CLEAR or NOT CLEAR!' \
                'Based on the following description, are there any obstacles in front of the viewer: ' + 
                whatisit['response'].strip() \
                ,
            stream=False)
        print("Obstacles: ", obstacles['response'].strip())
        
    except Exception as e:
        print('Error:', e)
        continue

    end_time = time.time()
    execution_time = end_time - start_time
    print("Execution time:", execution_time, "seconds")

    # Check if 'q' is pressed and if so, break the loop
    stop = False
    if cv2.waitKey(1000) & 0xFF == ord('q'):
        stop = True

    # Stop the thread
    if not thread.stopped:
        thread.stopped = True
        thread.join()

    if obstacles['response'].strip() in ['CLEAR', 'Clear', 'CLEAR!']:
        print("No obstacles in front, moving forward")
        move_forward()
    else:
        print("Obstacles detected, turning")
        if random.choice([True, False]):
            print("Turning left")
            turn_left()
        else:
            print("Turning right")
            turn_right()
    time.sleep(5)

# Release the video capture and close the window
subscriber.close()
publisher.close()
zmqcontext.term()
cv2.destroyAllWindows()
