#FROM osrf/ros:jazzy-desktop
FROM arm64v8/ros:jazzy-ros-base

RUN apt update && apt install -y --no-install-recommends \
   dialog apt-utils curl software-properties-common apt-transport-https wget git iputils-ping net-tools iproute2 vim build-essential ssh tmux tcpdump gdb busybox

RUN \
 busybox --install

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && apt install -y --no-install-recommends \
  ros-jazzy-rmw-zenoh-cpp

RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc
