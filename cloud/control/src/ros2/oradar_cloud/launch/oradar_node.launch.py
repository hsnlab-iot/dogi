from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='oradar_cloud',
            executable='oradar_node',
            name='oradar_node',
            output='screen',
        ),
    ])
