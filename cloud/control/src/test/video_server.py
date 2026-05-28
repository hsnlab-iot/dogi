import cv2
import zmq
import numpy as np
import threading
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler

# --- CONFIGURATION: Match these to your incoming ZMQ stream properties ---
FRAME_HEIGHT = 480
FRAME_WIDTH = 640
FRAME_CHANNELS = 3  # 3 for BGR color, 1 for Grayscale
PORT = 8888         # Port changed to 8888
# ------------------------------------------------------------------------

latest_jpeg_frame = None
frame_lock = threading.Lock()

def zmq_worker():
    global latest_jpeg_frame
    context = zmq.Context()
    subscriber = context.socket(zmq.SUB)
    subscriber.setsockopt(zmq.CONFLATE, 1)  # Drop old frames to maintain real-time speed
    subscriber.setsockopt_string(zmq.SUBSCRIBE, '')
    subscriber.connect("ipc:///tmp/dogi/video_frames_c.ipc")
    
    print("Connected to raw ZMQ IPC source. Encoding to JPEG...")
    
    while True:
        try:
            # 1. Receive raw uncompressed bytes
            frame_bytes = subscriber.recv()
            
            # 2. Reconstruct into a numpy array matrix
            frame_np = np.frombuffer(frame_bytes, dtype=np.uint8).reshape(FRAME_HEIGHT, FRAME_WIDTH, FRAME_CHANNELS)

            frame_bgr = cv2.cvtColor(frame_np, cv2.COLOR_RGB2BGR)
            
            # 3. Compress the raw matrix into JPEG format on the fly
            success, encoded_image = cv2.imencode('.jpg', frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            
            if success:
                # 4. Convert the encoded array back to raw JPEG string bytes
                jpeg_bytes = encoded_image.tobytes()
                with frame_lock:
                    latest_jpeg_frame = jpeg_bytes
                    
        except ValueError as val_err:
            print(f"Shape mismatch error: Make sure height/width config matches incoming bytes. Details: {val_err}")
        except Exception as e:
            print(f"ZMQ Worker Error: {e}")

class MJPEGHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global latest_jpeg_frame
        if self.path == '/stream.mjpg':
            # Disable HTTP logging for every frame to avoid filling up your console
            self.log_message = lambda format, *args: None
            
            self.send_response(200)
            self.send_header('Age', '0')
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            
            try:
                while True:
                    with frame_lock:
                        if latest_jpeg_frame is None:
                            continue
                        local_frame = latest_jpeg_frame
                    
                    self.wfile.write(b'--frame\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', str(len(local_frame)))
                    self.end_headers()
                    
                    self.wfile.write(local_frame)
                    self.wfile.write(b'\r\n')
            except Exception:
                # Client disconnected cleanly (e.g., OpenCV window closed)
                pass
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == '__main__':
    # Run the ZMQ parsing and encoding inside an independent background thread
    t = threading.Thread(target=zmq_worker, daemon=True)
    t.start()
    
    # Using ThreadingHTTPServer instead of HTTPServer handles concurrent multi-client demands
    server_address = ('0.0.0.0', PORT)
    httpd = ThreadingHTTPServer(server_address, MJPEGHandler)
    
    print(f"Multi-client MJPEG Network Stream ready at http://<your_ip>:{PORT}/stream.mjpg")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server...")
