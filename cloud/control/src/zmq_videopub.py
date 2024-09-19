import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject, GLib
import numpy as np
import zmq
import time
import threading
from PIL import Image, ImageDraw

reader = None
image_ok = Image.new('RGB', (64, 64), 'green')
image_nok = Image.new('RGB', (64, 64), 'red')

class H264Reader():

    def __init__(self, socket_c):
        
        self.last_c = time.time()
        self.rate_c = 0
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
        #print("!c")
        global socket_c
        sample = sink.emit("pull-sample")
        buffer = sample.get_buffer()

        # Get buffer size and extract buffer data
        buffer_size = buffer.get_size()
        buffer_data = buffer.extract_dup(0, buffer_size)

        # Convert buffer data to numpy array
        img_array = np.frombuffer(buffer_data, dtype=np.uint8)
        self.socket_c.send(img_array)

        self.rate_c = 1 / (time.time() - self.last_c)
        self.last_c = time.time()

        return Gst.FlowReturn.OK

def check_last_c(reader):

    while True:
        now = time.time()

        if now - reader.last_c < 0.1:
            draw = ImageDraw.Draw(image_ok)
            draw.rectangle([(0, 0), (64, 64)], fill='green')
            image_ok.show()
            print(reader.rate_c)
        else:
            draw = ImageDraw.Draw(image_nok)
            draw.rectangle([(0, 0), (64, 64)], fill='red')
            image_nok.show()
            print("No video")
        
        time.sleep(1)
    


def main():

    context = zmq.Context()
    socket_c = context.socket(zmq.PUB)
    socket_c.bind("ipc:///tmp/video_frames_c.ipc")

    Gst.init(None)
    reader = H264Reader(socket_c)


    # Create and start the thread
    thread = threading.Thread(target=check_last_c, args=(reader,))
    thread.start()

    event = threading.Event()
    event.wait()

if __name__ == '__main__':
    main()
