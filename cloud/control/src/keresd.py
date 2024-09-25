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

# OLLAMA_HOST should be set in the env or use localhost
ollama_client = ollama.Client(host='http://10.6.6.20:11434')

# Create a UDP socket to Dogi
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.connect(('localhost', 5002))

MAXPITCH = 20
MAXYAW = 16

# Subscribe to video
zmqcontext = zmq.Context()
subscriber = zmqcontext.socket(zmq.SUB)
subscriber.setsockopt(zmq.CONFLATE, 1)
subscriber.setsockopt_string(zmq.SUBSCRIBE, '')  # Subscribe to all topics
subscriber.connect("ipc:///tmp/video_frames_c.ipc")  # IPC socket address


def dogControl(command, args = None):
    if args:
        sock.send(pickle.dumps({'name': command, 'args': args}))
    else:
        sock.send(pickle.dumps({'name': command}))

def look_left():
    dogControl('attitude', (['r', 'p', 'y'], [0, MAXPITCH, -MAXYAW]))

def look_right():
    dogControl('attitude', (['r', 'p', 'y'], [0, MAXPITCH, MAXYAW]))

def look_front():
    dogControl('attitude', (['r', 'p', 'y'], [0, MAXPITCH, 0]))

def look_straint():
    dogControl('attitude', (['r', 'p', 'y'], [0, 0, 0]))

def move_forward():
    look_straint()
    dogControl('forward', (5, ))
    time.sleep(3)
    dogControl('stop')

def turn_left():
    look_straint()
    dogControl('turn', (5, ))
    time.sleep(3)
    dogControl('stop')

def turn_right():
    look_straint()
    dogControl('turn', (-5, ))
    time.sleep(3)
    dogControl('stop')

# Function to process the frame
def take_frame():
    
    frame_bytes = None
    try:
        frame_bytes = subscriber.recv()
    except zmq.error.Again:
        pass  # No frame received, continue processing

    if frame_bytes is None:
        return None

    width = 640
    height = 480
    img_array = np.frombuffer(frame_bytes, dtype=np.uint8)
    img_array = img_array.reshape((height, width, 3))
    img_array = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
    return img_array


def look_left_right():
    threading.current_thread().stopped = False
    while not threading.current_thread().stopped:
        look_left()
        time.sleep(1.5)
        if threading.current_thread().stopped:
            break
        look_right()
        time.sleep(1.5)
        if threading.current_thread().stopped:
            break
        look_straint()
        time.sleep(1.5)
    look_straint()

while True:

    sock.send(pickle.dumps({'name': 'reset'}))
    time.sleep(1)

    look_front()
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

    ball = None
    obstacles = None
    try:
        ball = ollama_client.generate(model='llava:13b', 
            prompt='This is a liveview capture taken by a front camera of a robot dog.' \
                'If there are any balls on the picture, Describe me with great details, where is the ball' \
                'If there are no balls on the picture, please say just a single word: NO.' \
                ,
            images=[img_buffer.tobytes()],
            stream=False)

        obstacles = ollama_client.generate(model='llava:13b', 
            prompt='This is a liveview capture taken by a front camera of a robot dog.' \
                'The robot dog is looking straight ahead and a bit down.' \
                'The robot dog is in a room with a grass like green floor.' \
                'List any obstacles in front of the robot dog with great details.' \
                'If there are not any obstacles on the picture, please say just a single word: CLEAR.' \
                ,
            images=[img_buffer.tobytes()],
            stream=False)
        
    except Exception as e:
        print('Error:', e)
        continue

    end_time = time.time()
    execution_time = end_time - start_time
    print("Execution time:", execution_time, "seconds")

    ballstr = ball['response'].strip()
    obstaclesstr = obstacles['response'].strip()

    print(ballstr)
    print(obstaclesstr)

    # Check if 'q' is pressed and if so, break the loop
    stop = False
    if cv2.waitKey(0) & 0xFF == ord('q'):
        stop = True

    # Stop the thread
    thread.stopped = True
    thread.join()

    if ballstr not in ['NO', 'No']:
        print("Ball detected, stopping")
        break

    if obstacles['response'].strip() == 'CLEAR':
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

# Release the video capture and close the window
subscriber.close()
zmqcontext.term()
cv2.destroyAllWindows()
