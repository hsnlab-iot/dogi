Web servers (using flask):

5050: (web_joy.py)    Joystick
5051: (web_video.py)  MJPEG stream from zmq input to the browser
5060: (web_voice.py)  Voice through the browser

6080: (noVNC)         X desktop for development

Services:

5002/UDP: (DOGZILLAProxyServer.py)  Actions to the dog API
5010/UDP: (web_voice.py)            TTS service, text is the content
5011/UDP: (web_voice.py)            EN->HU + TTS service, text is the content

Sockets:

/tmp/video_frames_c.ipc: (zmq_videopub.py)     Incoming video frames