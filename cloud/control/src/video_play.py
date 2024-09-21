import cv2
import zmq
import numpy as np

# Subscribe to video
zmqcontext = zmq.Context()
subscriber = zmqcontext.socket(zmq.SUB)
subscriber.setsockopt(zmq.CONFLATE, 1)
subscriber.setsockopt_string(zmq.SUBSCRIBE, '')  # Subscribe to all topics
subscriber.connect("ipc:///tmp/video_frames_c.ipc")  # IPC socket address

while True:
    try:
        frame_bytes = subscriber.recv()
        width = 640
        height = 480
        img_array = np.frombuffer(frame_bytes, dtype=np.uint8)
        img_array = img_array.reshape((height, width, 3))

        img_array = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
        cv2.imshow("Dogi video", img_array)
    
    except zmq.error.Again:
        pass  # No frame received, continue processing

    if cv2.waitKey(1) == ord('q'):
        break

# Release the video capture and close the window
subscriber.close()
zmqcontext.term()
cv2.destroyAllWindows()