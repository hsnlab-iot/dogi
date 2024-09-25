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


ollama_ip = os.environ.get('OLLAMA_IP')
if ollama_ip is None:
    raise ValueError('OLLAMA_IP environment variable is not set')
ollama_client = ollama.Client(host=f'http://{ollama_ip}:11434')

# Create a UDP sockets to Dogi
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.connect(('localhost', 5002))
# Create a UDP sockets to web page
sock_web = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock_web.connect(('localhost', 5003))

VOICE_PORT = 5010
ENVOICE_PORT = 5011

def send_text_and_wait_for_answer(port, text):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', port))
    sock.send(text.encode('utf-8'))
    response = sock.recv(2048).decode('utf-8')
    sock.close()
    if ':' in response:
        parts = response.split(':', 1)
        return float(parts[0]), parts[1].strip()

    return float(response)

MAXPITCH = 20
MAXYAW = 16

# Subscribe to video
zmqcontext = zmq.Context()
subscriber = zmqcontext.socket(zmq.SUB)
subscriber.setsockopt(zmq.CONFLATE, 1)
subscriber.setsockopt_string(zmq.SUBSCRIBE, '')  # Subscribe to all topics
subscriber.connect("ipc:///tmp/video_frames_c.ipc")  # IPC socket address

publisher = zmqcontext.socket(zmq.PUB)
publisher.bind("ipc:///tmp/video_frames_keresd.ipc")

#text = "Most labdakereső játékot fogok játszani. " \
#        "Rejtsd el a labdát és én megpróbálom megtalálni, hogy hol van. " \
#        "Igyekszem ügyesen mozogni és semmihez sem érni. "
#d = send_text_and_wait_for_answer(VOICE_PORT, text)
#time.sleep(d + 3)

d = send_text_and_wait_for_answer(VOICE_PORT, "Aki bújt, aki nem, indulok. Figyelj, keresni kezdek. ")
time.sleep(d)


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

def look_straight():
    dogControl('attitude', (['r', 'p', 'y'], [0, 0, 0]))

def move_forward():
    look_straight()
    time.sleep(1)
    dogControl('forward', (5, ))
    time.sleep(3)
    dogControl('stop')

def turn_left():
    look_straight()
    time.sleep(1)
    dogControl('turn', (5, ))
    time.sleep(3)
    dogControl('stop')

def turn_right():
    look_straight()
    time.sleep(1)
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

    publisher.send(frame_bytes)

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
        look_straight()
        time.sleep(1.5)
    look_straight()

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

    obstacles = None
    ball_found = False
    try:
        whatisit = ollama_client.generate(model='llava:13b', 
            prompt='This is a liveview capture taken by a front camera of a robot dog.' \
                'The robot dog is looking straight ahead and a bit down.' \
                'Make a short description, briefly what is on the picture!' \
                'Focus on the near objects, ignore far away objects!' \
                'Try to describe these objects relative to the center of the picture!'  \
                ,
            images=[img_buffer.tobytes()],
            stream=False)
        
        print("TTS")
        d, hutext = send_text_and_wait_for_answer(ENVOICE_PORT, whatisit['response'].strip())
        print("Description: ", whatisit['response'].strip())
        print("Leírás: ", hutext)
        sock_web.send(pickle.dumps({'action': 'hutext', 'text': hutext}))
        sock_web.send(pickle.dumps({'action': 'entext', 'text': whatisit['response'].strip()}))
        time.sleep(d)

        ball = ollama_client.generate(model='llama3.1', 
            prompt='Answer with a single word, YES or NO! Based on the following description, are there any balls in this description: ' + 
                whatisit['response'].strip() \
                ,
            stream=False)

        print("Ball: ", ball['response'].strip())

        if ball['response'].strip() in ['YES', 'Yes', 'YES!']:
            d = send_text_and_wait_for_answer(VOICE_PORT, "Hurrá, megtaláltam a labdát. ")
            time.sleep(d)            
            ball_found = True
            ball_place = ollama_client.generate(model='llava:13b', 
                prompt='This is a liveview capture taken by a front camera of a robot dog.' \
                    'Describe where you see the ball on the picture, and how does the ball look like' \
                    ,
                images=[img_buffer.tobytes()],
                stream=False)

            print("TTS")
            d, hutext = send_text_and_wait_for_answer(ENVOICE_PORT, ball_place['response'].strip())
            print("Ball place: ", ball_place['response'].strip())
            print("Labda helye: ", hutext)
            sock_web.send(pickle.dumps({'action': 'hutext', 'text': hutext}))
            sock_web.send(pickle.dumps({'action': 'entext', 'text': ball_place['response'].strip()}))
            time.sleep(d)
            print("Ball detected, stopping")

            # Stop the thread
            thread.stopped = True
            thread.join()
            break

        obstacles = ollama_client.generate(model='llama3.1', 
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
    thread.stopped = True
    thread.join()

    if obstacles['response'].strip() in ['CLEAR', 'Clear', 'CLEAR!']:
        print("No obstacles in front, moving forward")
        move_forward()
        time.sleep(8)
    else:
        print("Obstacles detected, turning")
        if random.choice([True, False]):
            print("Turning left")
            turn_left()
            time.sleep(8)
        else:
            print("Turning right")
            turn_right()
            time.sleep(8)

# Release the video capture and close the window
subscriber.close()
publisher.close()
zmqcontext.term()
cv2.destroyAllWindows()
