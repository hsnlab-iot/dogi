import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject, GLib
import numpy as np
import zmq
import time
import threading


class H264Reader():

    def __init__(self, socket_c):
        
        self.last_c = time.time()
        self.socket_c = socket_c

        # Create a GStreamer pipeline from string
        pipeline_str_c = "udpsrc port=5100 ! application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)H264 ! rtph264depay ! avdec_h264 ! videoconvert ! video/x-raw,format=RGB ! appsink name=sink-color"
        self.pipeline_c = Gst.parse_launch(pipeline_str_c)

        if not self.pipeline_c:
            self.get_logger().error("Pipeline could not be created")
            return

        # Retrieve the appsink element
        self.sink = self.pipeline_c.get_by_name("sink-color")
        self.sink.set_property("emit-signals", True)
        self.sink.connect("new-sample", self.on_new_sample_c)

        # Start playing
        self.pipeline_c.set_state(Gst.State.PLAYING)

    def on_new_sample_c(self, sink):
        print("!c")
        global socket_c
        sample = sink.emit("pull-sample")
        buffer = sample.get_buffer()

        # Get buffer size and extract buffer data
        buffer_size = buffer.get_size()
        buffer_data = buffer.extract_dup(0, buffer_size)

        # Convert buffer data to numpy array
        img_array = np.frombuffer(buffer_data, dtype=np.uint8)
        self.socket_c.send(img_array)

        now = time.time()
        print(f"{(now - self.last_c) * 1000} ms")
        self.last_c = now

        print("c!")
        return Gst.FlowReturn.OK

def main():

    context = zmq.Context()
    socket_c = context.socket(zmq.PUB)
    socket_c.bind("ipc:///tmp/video_frames_c.ipc")

    Gst.init(None)
    node = H264Reader(socket_c)

    event = threading.Event()
    event.wait()

if __name__ == '__main__':
    main()
