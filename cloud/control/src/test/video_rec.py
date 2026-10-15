import cv2
import zmq
import numpy as np
import argparse

# ---- Command line arguments ----
parser = argparse.ArgumentParser(description="Record video from ZMQ stream")
parser.add_argument('--show',  help='display video window (requires graphics display)')
parser.add_argument('--output', default='output.mp4',
                    help='output file name (default: output.mp4)')
parser.add_argument('--seconds', type=float, default=0,
                    help='auto-stop after N seconds (0 = run until Ctrl+C)')
args = parser.parse_args()

# ---- ZMQ setup ----
zmqcontext = zmq.Context()
subscriber = zmqcontext.socket(zmq.SUB)
subscriber.setsockopt(zmq.CONFLATE, 1)
subscriber.setsockopt(zmq.RCVTIMEO, 1000)
subscriber.setsockopt_string(zmq.SUBSCRIBE, '')
subscriber.connect("ipc:///tmp/video_frames_c.ipc")

# ---- Video writer setup ----
width, height = 640, 480
fps = 30.0

fourcc = cv2.VideoWriter_fourcc(*'mp4v')
video_writer = cv2.VideoWriter(args.output, cv2.CAP_FFMPEG, fourcc, fps, (width, height))

if not video_writer.isOpened():
    raise RuntimeError("VideoWriter failed to open")

frame_count = 0
import time
start = time.time()

try:
    while True:
        try:
            frame_bytes = subscriber.recv()
            frame = np.frombuffer(frame_bytes, dtype=np.uint8).reshape((height, width, 3))

            video_writer.write(frame)
            frame_count += 1

            # Optional display — only if requested and display exists
            if args.show:
                cv2.imshow("Dogi video + REC", frame)
                if cv2.waitKey(1) == ord('q'):
                    print("\n'q' pressed — stopping")
                    break

            if frame_count % 30 == 0:
                print(f"recorded {frame_count} frames", flush=True)

        except zmq.error.Again:
            pass

        # Optional auto-stop
        if args.seconds > 0 and time.time() - start > args.seconds:
            print("\nTime limit reached — stopping")
            break

except KeyboardInterrupt:
    print("\nCtrl+C — stopping")

finally:
    video_writer.release()
    subscriber.close()
    zmqcontext.term()
    if args.show:
        cv2.destroyAllWindows()
    print(f"Saved {args.output} with {frame_count} frames")
