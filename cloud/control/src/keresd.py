import cv2
import numpy as np
import zmq
import time
import socket
import pickle
import threading
import ollama
import base64
from PIL import Image
from io import BytesIO

# OLLAMA_HOST should be set in the env or use localhost
ollama_client = ollama.Client(host='http://10.6.6.20:11434')
#ollama_llm = Ollama(model=os.environ.get("VISION_MODEL", "llava"), base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))

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


def dogControl(command, args):
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
        look_right()
        time.sleep(1.5)
        look_straint()
        time.sleep(1.5)

def convert_to_base64(opencv_image):
    pil_image = Image.fromarray(cv2.cvtColor(opencv_image, cv2.COLOR_BGR2RGB))
    buffered = BytesIO()
    pil_image.save(buffered, format="JPEG")  # You can change the format if needed
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

while True:

    sock.send(pickle.dumps({'name': 'reset'}))
    time.sleep(1)

    look_front()
    time.sleep(1.5)
    front_pic = take_frame()
    
    # Display the three pics side by side
    cv2.imshow("Front", front_pic)
    cv2.waitKey(1)

    # Start the looking thread
    thread = threading.Thread(target=look_left_right)
    thread.start()

    # Save front_pic into the current folder in jpeg format
    filename = "front_pic_{}.jpeg".format(time.time())
    cv2.imwrite(filename, front_pic)

    is_success, img_buffer = cv2.imencode(".jpg", front_pic)

    #img_base64 = convert_to_base64(front_pic)
    print("Ask ollama to describe the image")
    try:
        response = ollama_client.generate(model='llava:13b', 
            prompt='describe this image and make sure to include anything notable about it (include text you see in the image):', 
            images=[img_buffer.tobytes()],
            stream=False)
        print(response)
    except Exception as e:
        print('Error:', e)
#    llm_with_media_context = ollama_llm.bind(images=[img_base64])
#    response = llm_with_media_context.invoke("Describe this image in detail.")
#    print(response)

    # Stop the thread when desired
    thread.stopped = True
    thread.join()

    # Check if 'q' is pressed and if so, break the loop
    if cv2.waitKey(0) & 0xFF == ord('q'):
        break


# Release the video capture and close the window
subscriber.close()
zmqcontext.term()
cv2.destroyAllWindows()
