from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='video_compression',
            executable='compress',
            name='compress_color',
            output='screen',
            remappings=[
                ('video/h264', 'video/color_h264')
            ],
            parameters=[
                {'zmq_url': 'ipc:///tmp/color_image'},
                {'mode': 'color'},
                {'width': 640},
                {'height': 480},
                {'bitrate': 2000}
            ]
        ),
        Node(
            package='video_compression',
            executable='compress',
            name='compress_depth',
            output='screen',
            remappings=[
                ('video/h264', 'video/depth_h264')
            ],
            parameters=[
                {'zmq_url': 'ipc:///tmp/depth_image'},
                {'mode': 'depth_yuv_12'},
                {'width': 640},
                {'height': 480},
                {'bitrate': 2000}
            ]
        )
    ])
