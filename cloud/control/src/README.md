Web servers (using flask):

5050: (web_joy.py)    Joystick
5051: (web_video.py)  MJPEG stream from zmq input to the browser
5052: (web_voice.py)  Voice through the browser
5053: (web_keresd.py) Keresd app
5054: (web_mutasd.py) Mutasd app

6080: (noVNC)         X desktop for development

Services:

5002/UDP: (DOGZILLAProxyServer.py)  Actions to the dog "API"
5003/UDP: (web_keresd.py)           "API" to the keresd app
5004/UDP: (web_mutasd.py)           "API" to the mutasd app
5010/TCP: (web_voice.py)            TTS service, text is the content
5011/TCP: (web_voice.py)            EN->HU + TTS service, text is the content

Sockets:

/tmp/video_frames_c.ipc: (zmq_videopub.py)     Incoming video frames
/tmp/video_frames_keresd.ipc: (keresd.py)      Processed frames
/tmp/video_frames_kovesd.ipc: (kovesd.py)      Processed frames
/tmp/video_frames_mutasd.ipc: (mutasd.py)      Processed frames
