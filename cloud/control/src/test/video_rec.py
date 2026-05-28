import cv2
import zmq
import numpy as np

# Subscribe to video
zmqcontext = zmq.Context()
subscriber = zmqcontext.socket(zmq.SUB)
subscriber.setsockopt(zmq.CONFLATE, 1)
subscriber.setsockopt_string(zmq.SUBSCRIBE, '')  # Subscribe to all topics
subscriber.connect("ipc:///tmp/video_frames_c.ipc")  # IPC socket address

# Define the output video file
output_file = 'output.mp4'

width = 640
height = 480

# Define the codec and create a VideoWriter object
fourcc = cv2.VideoWriter_fourcc(*'H264')
video_writer = cv2.VideoWriter(output_file, fourcc, 30.0, (width, height))

while True:
    try:
        frame_bytes = subscriber.recv()
        img_array = np.frombuffer(frame_bytes, dtype=np.uint8)
        img_array = img_array.reshape((height, width, 3))

        img_array = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
        cv2.imshow("Dogi video + REC", img_array)

        # Write the frame to the video file
        video_writer.write(img_array)

    except zmq.error.Again:
        pass  # No frame received, continue processing

    if cv2.waitKey(1) == ord('q'):
        break

# Release the video writer, video capture, and close the window
video_writer.release()
subscriber.close()
zmqcontext.term()
cv2.destroyAllWindows()