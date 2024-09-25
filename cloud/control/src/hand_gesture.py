import cv2
import numpy as np
import zmq
import time
import math
#from DOGZILLALib.DOGZILLALib import DOGZILLALib as dog
import socket
import pickle

import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from mediapipe import solutions
from mediapipe.framework.formats import landmark_pb2

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles


model_path = '/root/gesture_recognizer.task'

# hand landmarker source: 
# https://colab.research.google.com/github/googlesamples/mediapipe/blob/main/examples/hand_landmarker/python/hand_landmarker.ipynb#scrollTo=OMjuVQiDYJKF
# https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/index#models

# hand gesture source:
# https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/latest/gesture_recognizer.task
# https://ai.google.dev/edge/mediapipe/solutions/vision/gesture_recognizer/index#models


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

# GestureRecognizer object.
base_options = python.BaseOptions(model_asset_path='gesture_recognizer.task')
options = vision.GestureRecognizerOptions(base_options=base_options)
recognizer = vision.GestureRecognizer.create_from_options(options)

def resize_and_show(image):
  h, w = image.shape[:2]
  if h < w:
    img = cv2.resize(image, (DESIRED_WIDTH, math.floor(h/(w/DESIRED_WIDTH))))
  else:
    img = cv2.resize(image, (math.floor(w/(h/DESIRED_HEIGHT)), DESIRED_HEIGHT))
  return img



# Function to process the frame
def process_frame(frame_bytes):
    
    width = 640
    height = 480
    img_array = np.frombuffer(frame_bytes, dtype=np.uint8)
    img_array = img_array.reshape((height, width, 3))
    img_array = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)

    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_array)

    cv2.imshow("asd: ", img_array)
    # recognition_result = recognizer.recognize(image)

    return image
    

def display_image_with_hand_landmarks(frame_bytes):
    """Displays a single image with the gesture category, score, and hand landmarks using OpenCV (cv2.imshow)."""

    result = []
    width = 640
    height = 480
    img_array = np.frombuffer(frame_bytes, dtype=np.uint8)
    img_array = img_array.reshape((height, width, 3))
    img_array = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
  
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_array)


    recognition_result = recognizer.recognize(image)
    top_gesture = recognition_result.gestures[0][0]
    hand_landmark = recognition_result.hand_landmark
    result.append((top_gesture, hand_landmark))

    # Convert image to numpy view.
    image = image.numpy_view()

    # Extract the top gesture and the hand landmarks from the result.
    top_gesture, multi_hand_landmarks = result
    
    # Annotate image with hand landmarks.
    annotated_image = image.copy()
    
    for hand_landmarks in multi_hand_landmarks:
        hand_landmarks_proto = landmark_pb2.NormalizedLandmarkList()
        hand_landmarks_proto.landmark.extend([
            landmark_pb2.NormalizedLandmark(x=landmark.x, y=landmark.y, z=landmark.z) 
            for landmark in hand_landmarks
        ])
        
        mp_drawing.draw_landmarks(
            annotated_image,
            hand_landmarks_proto,
            mp_hands.HAND_CONNECTIONS,
            mp_drawing_styles.get_default_hand_landmarks_style(),
            mp_drawing_styles.get_default_hand_connections_style()
        )
    
    # Create a title for the window with gesture category and score
    # window_title = f"{top_gesture.category_name} ({top_gesture.score:.2f})"
    
    # Display the annotated image using OpenCV
    # cv2.imshow(window_title, annotated_image)
    return annotated_image

while True:

    try:
        frame_bytes = subscriber.recv()
    except zmq.error.Again:
        pass  # No frame received, continue processing
    
    if frame_bytes is None:
        break


    # print("\nresult: ", result)
    if result.gestures!=[] :
      print("top gesture: ", result.gestures[0][0], "hand_landmarks", result.hand_landmarks)





    # Display the result on the screen
    if cv2.waitKey(1) == ord('q'):
        break

# Release the video capture and close the window
subscriber.close()
zmqcontext.term()
cv2.destroyAllWindows()
