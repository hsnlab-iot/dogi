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

PORT = 5053

MAXPITCH = 20
MAXYAW = 16

DEBUG_mode = os.getenv('DEBUG', '0') == '1'

config.init()

# Create a UDP sockets to web page server
sock_web = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock_web.connect(('localhost', PORT))

# Subscribe to video
zmqcontext = zmq.Context()
subscriber = zmqcontext.socket(zmq.SUB)
subscriber.setsockopt(zmq.CONFLATE, 1)
subscriber.setsockopt_string(zmq.SUBSCRIBE, '')  # Subscribe to all topics
subscriber.connect("ipc:///tmp/video_frames_c.ipc")  # IPC socket address

publisher = zmqcontext.socket(zmq.PUB)
publisher.bind("ipc:///tmp/video_frames_keresd.ipc")

text = {
    'en': "Let's play a ball finding game! Ready or not, here I come! I'm starting to look!",
    'hu': "Játsszunk labdakereső játékot! Aki bújt, aki nem, indulok. Figyelj, keresni kezdek."
}
xtext = utils.select_text(text, config.get_ui_language(), True)
print(xtext)
wav, d = utils.tts_wav(xtext)
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

while True:

    utils.dogy_reset()
    time.sleep(1)

    utils.dogy_look(0, MAXPITCH, 0) # Look front
    time.sleep(1.5)
    
    front_pic = None
    if DEBUG_mode:
        jpg_files = glob.glob("/root/debug/*.jpeg")
        if jpg_files:
            random_file = random.choice(jpg_files)
            front_pic = cv2.imread(random_file)
            print(f"Loaded random picture: {random_file}")
        else:
            print("No jpeg files found in the folder.")
    else:
        front_pic = take_frame()
        # Save front_pic into the current folder in jpeg format
        filename = "front_pic_{}.jpeg".format(time.time())
        cv2.imwrite(filename, front_pic)
        print(f"Saved picture: {filename}")

    # Display the picture
    cv2.imshow("Front", front_pic)
    cv2.waitKey(1)

    # Start the looking thread
    thread = threading.Thread(target=look_left_right)
    thread.start()

    is_success, img_buffer = cv2.imencode(".jpg", front_pic)

    start_time = time.time()
    obstacles = None
    ball_found = False

    try:
        prompt_text = {
            'hu': 'Ez egy robotkutyára szerelt első kamera által készített élő nézet. '\
                'A robotkutya egyenesen előre és kissé lefelé néz. '\
                'Készíts egy rövid leírást, mi látható a képen! '\
                'Koncentrálj a közeli tárgyakra, hagyd figyelmen kívül a távoli tárgyakat! '\
                'Próbáld meg ezeket a tárgyakat a kép közepéhez viszonyítva leírni! ' \
                'Ha labda lenne a képen, feltétlenül említsd meg!',
            'en': 'This is a liveview capture taken by a front camera of a robot dog.' \
                'The robot dog is looking straight ahead and a bit down.' \
                'Make a short description, what is on the picture!' \
                'Focus on the near objects, ignore far away objects!' \
                'Try to describe these objects relative to the center of the picture!' \
                'If there is a ball on the picture, be sure to mention it!'
        }
        text = utils.prompt(prompt_text, images=[img_buffer.tobytes()])
        print(f"Description: {text}")
        sock_web.send(pickle.dumps({'action': 'entext', 'text': text}))

        if config.needs_translation():
            print("Ask translation" )
            xtext = utils.translate(text, config.get_prompt_language())
            print("Translation: ", xtext)
            sock_web.send(pickle.dumps({'action': 'xtext', 'text': xtext}))
        else:
            xtext = text

        print("Ask for TTS")
        wav, d = utils.tts_wav(xtext)
        utils.play_wav(wav)
        time.sleep(d)

        prompt_text = {
            'hu': 'Válaszolj egyetlen szóval, IGEN vagy NEM ! '\
                'Van-e bármilyen labda ebben a leírásban: ' + \
                text,
            'en': 'Answer with a single word, YES or NO ! '\
                'Are there any balls in this description: ' + \
                text
        }
        ball = utils.prompt(prompt_text)
        print("Ball: ", ball)

        if ball.upper() in ['YES', 'YES!', 'IGEN', 'IGEN!']:
            text = {
                'hu': "Hurrá, megtaláltam a labdát!",
                'en': "Hooray, I found a ball!"
            }
            xtext = utils.select_text(text, config.get_ui_language(), True)
            wav, d = utils.tts_wav(xtext)
            utils.play_wav(wav)
            time.sleep(d)

            ball_found = True

            prompt_text = {
                'hu': 'Ez egy robotkutyára szerelt első kamera által készített élő nézet. '\
                    'Írd le, hogy hol látod a képen a labdát, és hogy néz ki a labda!' \
                    ,
                'en': 'This is a liveview capture taken by a front camera of a robot dog.' \
                    'Describe where you see the ball on the picture, and how does the ball look like' \
                    ,
            }
            text = utils.prompt(prompt_text, images=[img_buffer.tobytes()])
            print(f"Ball place: {text}")
            sock_web.send(pickle.dumps({'action': 'entext', 'text': text}))

            if config.needs_translation():
                print("Ask translation" )
                xtext = utils.translate(text, config.get_prompt_language())
                print("Translation: ", xtext)
                sock_web.send(pickle.dumps({'action': 'xtext', 'text': xtext}))
            else:
                xtext = text

            print("TTS")
            wav, d = utils.tts_wav(xtext)
            utils.play_wav(wav)
            time.sleep(d)

            print("Ball detected, stopping")

            # Stop the thread
            thread.stopped = True
            thread.join()
            break

        prompt_text = {
            'en': 'Answer with a single word, YES or NO ! ' \
                'Based on the following image, are there any near obstacles in front of the viewer? ',
            'hu': 'Válaszolj egyetlen szóval, IGEN vagy NEM ! ' \
                'A következő kép alapján van akadály köyvetlenül a néző előtt? '
        }
        obstacles = utils.prompt(prompt_text, images=[img_buffer.tobytes()])
        print("Obstacles: ", obstacles)
        
    except Exception as e:
        print('Error:', e)
        continue

    print("Execution time: ", time.time() - start_time, " seconds")

    # Check if 'q' is pressed and if so, break the loop
    stop = False
    if cv2.waitKey(1000) & 0xFF == ord('q'):
        stop = True

    # Stop the thread
    if not thread.stopped:
        thread.stopped = True
        thread.join()

    if not (obstacles.upper in ['YES', 'YES!', 'IGEN', 'IGEN!']):
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
