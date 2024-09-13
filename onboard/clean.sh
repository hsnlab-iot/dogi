#!/bin/bash

# Kill the app
sh /home/pi/DOGZILLA/app_dogzilla/kill_dogzilla.sh
# Stop the Gnome Shell
sudo systemctl stop gdm
# Stop NX
sudo systemctl stop nxserver.service
# Stop jupyter
sudo systemctl stop yahboom_jupyterlab.service
# Stop snapd
#sudo systemctl stop snapd

# Stop ros2
sudo systemctl stop YahboomStart
#ps -ef | grep ros2 | awk '{print $2}' | sudo xargs kill -9
