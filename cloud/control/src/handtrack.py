import cv2
import numpy as np
import zmq
import time
#from DOGZILLALib.DOGZILLALib import DOGZILLALib as dog
import socket
import pickle

import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles
mp_hands = mp.solutions.hands

MARGIN = 10  # pixels
FONT_SIZE = 1
FONT_THICKNESS = 1
HANDEDNESS_TEXT_COLOR = (88, 205, 54) # vibrant green

model_path = '/hand_landmarker.task'

# source: 
# https://colab.research.google.com/github/googlesamples/mediapipe/blob/main/examples/hand_landmarker/python/hand_landmarker.ipynb#scrollTo=OMjuVQiDYJKF
# https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/index#models

#dogControl = dog.DOGZILLA("/dev/ttyAMA0")

# Create a UDP socket to Dogi
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.connect(('localhost', 5002))

time.sleep(1)   # Wait for the dogControl


# Subscribe to video
zmqcontext = zmq.Context()
subscriber = zmqcontext.socket(zmq.SUB)
subscriber.setsockopt(zmq.CONFLATE, 1)
subscriber.setsockopt_string(zmq.SUBSCRIBE, '')  # Subscribe to all topics
subscriber.connect("ipc:///tmp/video_frames_c.ipc")  # IPC socket address



# Draw the hand joints
def draw_landmarks_on_image(rgb_image, detection_result):
  hand_landmarks_list = detection_result.hand_landmarks
  handedness_list = detection_result.handedness
  annotated_image = np.copy(rgb_image)

  # Loop through the detected hands to visualize.
  for idx in range(len(hand_landmarks_list)):
    hand_landmarks = hand_landmarks_list[idx]
    handedness = handedness_list[idx]

    # Draw the hand landmarks.
    hand_landmarks_proto = landmark_pb2.NormalizedLandmarkList()
    hand_landmarks_proto.landmark.extend([
      landmark_pb2.NormalizedLandmark(x=landmark.x, y=landmark.y, z=landmark.z) for landmark in hand_landmarks
    ])
    solutions.drawing_utils.draw_landmarks(
      annotated_image,
      hand_landmarks_proto,
      solutions.hands.HAND_CONNECTIONS,
      solutions.drawing_styles.get_default_hand_landmarks_style(),
      solutions.drawing_styles.get_default_hand_connections_style())

    # Get the top left corner of the detected hand's bounding box.
    height, width, _ = annotated_image.shape
    x_coordinates = [landmark.x for landmark in hand_landmarks]
    y_coordinates = [landmark.y for landmark in hand_landmarks]
    text_x = int(min(x_coordinates) * width)
    text_y = int(min(y_coordinates) * height) - MARGIN

    # Draw handedness (left or right hand) on the image.
    cv2.putText(annotated_image, f"{handedness[0].category_name}",
                (text_x, text_y), cv2.FONT_HERSHEY_DUPLEX,
                FONT_SIZE, HANDEDNESS_TEXT_COLOR, FONT_THICKNESS, cv2.LINE_AA)

  return annotated_image

# Function to process the frame
def process_frame(frame_bytes):
    global att, att_changed
    
    width = 640
    height = 480
    img_array = np.frombuffer(frame_bytes, dtype=np.uint8)
    img_array = img_array.reshape((height, width, 3))

    base_options = python.BaseOptions(model_asset_path='hand_landmarker.task')
    options = vision.HandLandmarkerOptions(base_options=base_options,
                                        num_hands=2)
    detector = vision.HandLandmarker.create_from_options(options)

    # STEP 4: Detect hand landmarks from the input image.
    detection_result = detector.detect(img_array)

    # STEP 5: Process the classification result. In this case, visualize it.
    annotated_image = draw_landmarks_on_image(img_array.numpy_view(), detection_result)

    return annotated_image
    

while True:

    try:
        frame_bytes = subscriber.recv()
        hands = process_frame(frame_bytes)
        cv2.imshow("annotated hands", hands)

    except zmq.error.Again:
        pass  # No frame received, continue processing

    # Display the result on the screen
    if cv2.waitKey(1) == ord('q'):
        break

# Release the video capture and close the window
subscriber.close()
zmqcontext.term()
cv2.destroyAllWindows()
