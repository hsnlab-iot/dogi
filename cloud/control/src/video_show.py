import cv2
import zmq
import numpy as np
import yaml

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

        # Camera matrix
        camera_matrix = np.array([[944.012173, 0.000000, 534.248944],
                                  [0.000000, 893.428920, 358.594765],
                                  [0.000000, 0.000000, 1.000000]])

        dist_coeffs = np.array([0.260086, -0.025048, 0.089063, 0.138628, 0.000000])

        newcameramatrix, _ = cv2.getOptimalNewCameraMatrix(
           camera_matrix, dist_coeffs, (width, height), 1, (width, height)
        )
        undistorted_img = cv2.undistort(
           img_array, camera_matrix, dist_coeffs, None, newcameramatrix
        )   
        
        # Undistort the image
        #undistorted_img = cv2.undistort(img_array, camera_matrix, dist_coeffs)

        # Display the undistorted image
        cv2.imshow("Undistorted Image", undistorted_img)
        cv2.imshow("Dogi video", img_array)
    
    except zmq.error.Again:
        pass  # No frame received, continue processing

    if cv2.waitKey(1) == ord('q'):
        break

# Release the video capture and close the window
subscriber.close()
zmqcontext.term()
cv2.destroyAllWindows()