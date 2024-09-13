import cv2
import numpy as np
import zmq
import time
from ultralytics import YOLO
from DOGZILLALib.DOGZILLALib import DOGZILLALib as dog


model = YOLO('yolov8m-seg.pt')
dogControl = dog.DOGZILLA("/dev/ttyAMA0")

MAXPITCH = 10
MAXYAW = 10

# Subscribe to video
zmqcontext = zmq.Context()
subscriber = zmqcontext.socket(zmq.SUB)
subscriber.setsockopt(zmq.CONFLATE, 1)
subscriber.setsockopt_string(zmq.SUBSCRIBE, '')  # Subscribe to all topics
subscriber.connect("ipc:///tmp/video_frames_c.ipc")  # IPC socket address

att = [0, 0 ,0] # yaw, pitch, roll
att_changed = True
turn = 0
oldturn = 0

time.sleep(1)   # Wait for the dogControl

def process_frame(frame_bytes):
    
    width = 640
    height = 480
    img_array = np.frombuffer(frame_bytes, dtype=np.uint8)
    img_array = img_array.reshape((height, width, 3))
    cv2.imshow("YOLO Object Detection", img_array)
    return

    results = model.track(img_array, imgsz=[height, width], conf=0.4, persist=True)
    annotated_frame = results[0].plot()
    
    cv2.imshow("YOLO Object Detection", annotated_frame)

def process_keys():
    global att_changed
    global turn

    if turn > 0:
        turn-=1
    elif turn < 0:
        turn+=1

    key = cv2.waitKey(1)
    if key == ord('s'):
        if att[1] < MAXPITCH:
            att[1] += 1
            att_changed = True
    elif key == ord('w'):
        if att[1] > -MAXPITCH:
            att[1] -= 1
            att_changed = True
    elif key == ord('a'):
        if att[0] < MAXYAW:
            att[0] += 1
            att_changed = True
        else:
            turn = 3
    elif key == ord('d'):
        if att[0] > -MAXYAW:
            att[0] -= 1
            att_changed = True
        else:
            turn = -3

while True:

    try:
        frame_bytes = subscriber.recv()
        process_frame(frame_bytes)
        process_keys()
        if att_changed:
            print("ATTITUDE")
            dogControl.attitude(["y", "p", "r"], att)
            att_changed = False
        if turn != oldturn:
            print("TURN", turn)
            if turn > 0:
                dogControl.turn(10)
            elif turn < 0:
                dogControl.turn(-10)
            else:
                dogControl.stop()
            oldturn = turn

    except zmq.error.Again:
        pass  # No frame received, continue processing

    # Display the result on the screen
    if cv2.waitKey(1) == ord('q'):
        break

# Release the video capture and close the window
subscriber.close()
zmqcontext.term()
cv2.destroyAllWindows()