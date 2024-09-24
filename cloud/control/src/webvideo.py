import time
import numpy as np
import zmq
import cv2
from flask import Flask, Response
from threading import Thread, Lock

# Subscribe to video
zmqcontext = zmq.Context()
subscriber = zmqcontext.socket(zmq.SUB)
subscriber.setsockopt(zmq.CONFLATE, 1)
subscriber.setsockopt_string(zmq.SUBSCRIBE, '')  # Subscribe to all topics
subscriber.connect("ipc:///tmp/video_frames_c.ipc")  # IPC socket address

last_frame = None
lock = Lock()

app = Flask(__name__)

def gen_mjpeg():
    while True:
        frame = None
        with lock:
            frame = last_frame.copy()
        yield (b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + frame.tobytes() + b'\r\n')
        time.sleep(1/25)
    
@app.route("/mjpeg")
def mjpeg():
    return Response(gen_mjpeg(), mimetype='multipart/x-mixed-replace; boundary=frame')

def get_frames():
    global last_frame

    while True:
        try:
            frame_bytes = subscriber.recv()
            width = 640
            height = 480
            img_array = np.frombuffer(frame_bytes, dtype=np.uint8)
            img_array = img_array.reshape((height, width, 3))

            img_array = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
            _, frame = cv2.imencode('.jpg', img_array)
            with lock:
                last_frame = frame.copy()

        except zmq.error.Again:
            pass  # No frame received, continue processing

if __name__ == '__main__':
    
    thread = Thread(target=get_frames)
    thread.start()

    app.run(host='0.0.0.0', port=5051, threaded=True)

