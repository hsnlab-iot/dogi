#!/bin/bash -x

#tmux new-session -d -s realhebi "source /opt/ros/humble/setup.bash; cd /opt/ws/;. install/setup.bash;ros2 launch realhebi k8s-realhebi.launch.py; sleep inf"

tmux new-session -d -s sick_frames "source /opt/ws/install/setup.bash && ros2 launch smartamr staticframes.launch.py && sleep inf"
tmux new-session -d -s sickpublisher "source /opt/ws/install/setup.bash && ros2 run smartamr sickpublisher && sleep inf"

tail -f /dev/null
