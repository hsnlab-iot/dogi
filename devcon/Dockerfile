# Use the official Ubuntu base image
FROM ubuntu:latest

# Update the package lists
RUN apt-get update

# Install essential build tools and libraries for C++ development
RUN apt-get install -y build-essential cmake busybox && busybox --install

# Copy the MS200 SDK file to the container
COPY MS200_Ros-V1.3.4.zip /app/

# Unzip the file
RUN \
 cd /app && unzip MS200_Ros-V1.3.4.zip && \
 cd /app/p2117_ros/oradar_ros/sdk && \
 mkdir build && cd build && \
 cmake .. && make install

# Set the entry point for the container
CMD ["bash"]