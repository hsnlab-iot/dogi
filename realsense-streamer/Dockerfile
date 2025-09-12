FROM ros_base:2506

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
 libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
 gstreamer1.0-tools \
 gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
 gstreamer1.0-plugins-ugly gstreamer1.0-plugins-base-apps gstreamer1.0-libav \
 libzmq3-dev \
 python3-pkgconfig pkg-config \
 python3-zmq python3-venv \
 pip

RUN apt-get install -y --no-install-recommends \
    ros-jazzy-depth-image-proc

SHELL ["/bin/bash", "-c"]

RUN \
 add-apt-repository ppa:deadsnakes/ppa && apt update && \
 apt install -y --no-install-recommends \
  python3.11 python3.11-venv python3.11-distutils python3.11-dev 
#  python3.10 python3.10-venv python3.10-distutils python3.10-dev

#RUN \
# python3.10 -m venv /opt/venv310 && \
# source /opt/venv310/bin/activate && \
# python3.10 -m pip install --upgrade pip && \
# python3.10 -m pip install pyrealsense2==2.55.1.6486 numpy zmq

RUN \
 python3.11 -m venv /opt/venv311 && \
 source /opt/venv311/bin/activate && \
 python3.11 -m pip install --upgrade pip && \
 python3.11 -m pip install numpy zmq

ARG CACHEBUST=1
RUN  \
 mkdir -p /opt/ws/src && \
 git clone https://github.com/hsnlab-iot/ros2_rs_video.git /opt/ws/src/ros2_rs_video

RUN \
 source /opt/ros/jazzy/setup.bash && cd /opt/ws && \
 colcon build --symlink-install --mixin release

COPY launch /opt/ws/launch
COPY src/ /opt/ws

COPY docker-entrypoint.sh /usr/bin
RUN chmod +x /usr/bin/docker-entrypoint.sh

ENTRYPOINT [ "bash", "/usr/bin/docker-entrypoint.sh" ]
