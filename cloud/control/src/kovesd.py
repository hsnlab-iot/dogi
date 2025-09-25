import cv2
import numpy as np
import zmq
import time
from ultralytics import YOLO
#from DOGZILLALib.DOGZILLALib import DOGZILLALib as dog
import socket
import pickle

import utils

model = YOLO('yolov8m-seg.pt')
#dogControl = dog.DOGZILLA("/dev/ttyAMA0")
#time.sleep(1)   # Wait for the dogControl

MAXPITCH = 20
MAXYAW = 16
TURNBASE = 7

# Subscribe to video
zmqcontext = zmq.Context()
subscriber = zmqcontext.socket(zmq.SUB)
subscriber.setsockopt(zmq.CONFLATE, 1)
subscriber.setsockopt_string(zmq.SUBSCRIBE, '')  # Subscribe to all topics
subscriber.connect("ipc:///tmp/video_frames_c.ipc")  # IPC socket address

publisher = zmqcontext.socket(zmq.PUB)
publisher.bind("ipc:///tmp/video_frames_kovesd.ipc")

xtext = ""
if utils.get_language() == "Hungarian":
    xtext = "Most labdakövetős játékot fogok játszani. " \
            "Mozgasd a labdát előttem és én követni fogom. " \
            "Ha éppem nem látom a labdát, akkor nem mozdulok. "
else:
    text = "Now I will play a ball-following game. " \
        "Move the ball in front of me and I will follow it. " \
        "If I don't see the ball, I won't move. "
    xtext = utils.translate("English", text)

print("Text to speech: " + xtext)

wav, d = utils.tts_wav(xtext)
utils.play_wav(wav)
#time.sleep(d)

# Function to process the frame
def process_frame(frame_bytes):
    global att, att_changed
    
    width = 640
    height = 480
    img_array = np.frombuffer(frame_bytes, dtype=np.uint8)
    img_array = img_array.reshape((height, width, 3))

    #img_array = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
    #cv2.imshow("Dogi video", img_array)

    results = model.track(img_array, imgsz=[height, width], conf=0.25, classes=[32], verbose=False, persist=True)
    annotated_frame = results[0].plot()
    
    publisher.send(annotated_frame.tobytes())

    annotated_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
    cv2.imshow("YOLO Dogi video", annotated_frame)
    #print(result[0].boxes.xywhn)

    if len(results[0].boxes.xywhn) > 0:
        #print(results[0].boxes.xywhn[0])
        #print(results[0].boxes.cls)
        (x, y, w, h) = results[0].boxes.xywhn[0].cpu().numpy()
        x = round(x,2)
        y = round(y,2)
        return (x, y)
    else:
        return None
    

att_yaw = 0
o_att_yaw = 0
att_pitch = 0
o_att_pitch = 0
skip = 0

turn = 0
o_turn = 0

while True:

    try:
        frame_bytes = subscriber.recv()
        ball = process_frame(frame_bytes)

        if skip > 0:
            skip -= 1
            continue

        if ball:
            (x, y) = ball
            if turn > 0:
                if x < 0.5:
                    turn = TURNBASE    # Continue turn left
                else:
                    turn = 0
                    skip - 3    # Stop turning and pause
            elif turn < 0:
                if x > 0.5:
                    turn = -TURNBASE   # Continue turn right
                else:
                    turn = 0
                    skip = 3    # Stop turning and pause
            else:   # No turn in progress
                if x < 0.5:
                    if att_yaw == MAXYAW:
                        att_yaw = 0
                        turn = TURNBASE    # Start turning left
                        skip = 10
                    else:
                        att_yaw += 1    # Lean left
                elif x > 0.5:
                    if att_yaw == -MAXYAW:
                        att_yaw = 0
                        turn = -TURNBASE   # Start turning right
                        skip = 10
                    else:
                        att_yaw -= 1    # Lean right
            
                if y < 0.5 and att_pitch > -MAXPITCH:
                    att_pitch -= 1
                if y > 0.5 and att_pitch < MAXPITCH:
                    att_pitch += 1
        
        if turn != o_turn:
            o_turn = turn
            print("TURN", turn)
            if turn > 0:
                utils.dogy_control('turn', (10, ))
            elif turn < 0:
                utils.dogy_control('turn', (-10, ))
            else:
                utils.dogy_control('stop')
                att_yaw = 0 # Reset the attitude yaw

        elif att_yaw != o_att_yaw or att_pitch != o_att_pitch:
            o_att_yaw = att_yaw
            o_att_pitch = att_pitch 
            #print("ATTITUDE", att_yaw, att_pitch)
            utils.dogy_control('attitude', (["y", "p", "r"], [att_yaw, att_pitch, 0]))

        if turn > 0:
            turn -= 1
        elif turn < 0:
            turn += 1


    except zmq.error.Again:
        pass  # No frame received, continue processing

    # Display the result on the screen
    if cv2.waitKey(1) == ord('q'):
        break

# Release the video capture and close the window
subscriber.close()
publisher.close()
zmqcontext.term()
cv2.destroyAllWindows()
