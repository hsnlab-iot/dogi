#include <cstdio>

#include <thread>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

#include "oradar_cloud/ordlidar_protocol.h"

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/laser_scan.hpp>

class LidarNode : public rclcpp::Node {
public:
  LidarNode() : Node("lidar_node") {
    publisher_ = this->create_publisher<sensor_msgs::msg::LaserScan>("/scan", 10);

    // Get the UDP port number as a ROS parameter
    this->declare_parameter<int>("udp_port", 5005);
    udpPort_ = this->get_parameter("udp_port").as_int();

    // Start a separate thread for receiving UDP packets
    udpThread_ = new std::thread([this]() { receiveUDPData(); });
  }

  void receiveUDPData() {

    // Initialize and configure your UDP socket for receiving lidar data
    int sockFd_ = socket(AF_INET, SOCK_DGRAM, 0);
    if (sockFd_ < 0) {
      RCLCPP_ERROR(this->get_logger(), "Failed to create socket");
      return;
    }

    struct sockaddr_in serverAddr;
    serverAddr.sin_family = AF_INET;
    serverAddr.sin_port = htons(udpPort_);
    serverAddr.sin_addr.s_addr = INADDR_ANY;

    if (bind(sockFd_, (struct sockaddr*)&serverAddr, sizeof(serverAddr)) < 0) {
      RCLCPP_ERROR(this->get_logger(), "Failed to bind socket");
      close(sockFd_);
      return;
    }

    RCLCPP_INFO(this->get_logger(), "Receiving UDP LIDAR stream");

    char packet[sizeof(full_scan_data_st)+8];
    uint16_t* numBytes = reinterpret_cast<uint16_t*>(packet + 4);
    uint16_t* numPoints = reinterpret_cast<uint16_t*>(packet + 6);
    full_scan_data_st* scan_data_ptr = reinterpret_cast<full_scan_data_st*>(packet + 8);

    //struct sockaddr_in clientAddr;
    //socklen_t clientAddrLen = sizeof(clientAddr);

    while (true) {
      
      // Check if sockFd_ is open
      if (sockFd_ < 0) {
        RCLCPP_ERROR(this->get_logger(), "Socket is not open");
        return;
      }
      ssize_t bytesRead = recv(sockFd_, packet, sizeof(packet), 0);

      // Print the size of the received data
      RCLCPP_INFO(this->get_logger(), "Received data size: %zd", bytesRead);

      if (bytesRead < 0) {
        RCLCPP_WARN(this->get_logger(), "Failed to receive data");
        continue;
      }

      // Check if the first 4 bytes of the packet are "DOGI"
      if (strncmp(packet, "DOGI", 4) != 0) {
        RCLCPP_WARN(this->get_logger(), "Invalid packet header");
        continue;
      }

      // Check if the number of bytes received matches the value in *numBytes
      if (*numBytes != bytesRead) {
        RCLCPP_WARN(this->get_logger(), "Mismatch in packet size");
        continue;
      }
      scan_data_ptr->vailtidy_point_num = *numPoints;

      // Process the lidar data
      processLidarData(scan_data_ptr);
    }
  }

  void processLidarData(full_scan_data_st* scan_data_ptr)
  {
    // Create a sensor_msgs::msg::LaserScan message
    sensor_msgs::msg::LaserScan laserScanMsg;

    // Set the necessary fields of the message
    laserScanMsg.header.stamp = this->get_clock()->now();
    laserScanMsg.header.frame_id = "lidar_frame"; // Replace "lidar_frame" with the appropriate frame ID

    // THESE VALUES SHOULD BE IN RADIAN !!! Now they are in degree
    laserScanMsg.angle_min = scan_data_ptr->data[0].angle;
    laserScanMsg.angle_max = scan_data_ptr->data[scan_data_ptr->vailtidy_point_num-1].angle;
    laserScanMsg.angle_increment = 0.81; // This could be calculated, but lets be lazy

    laserScanMsg.range_min = 0.5; 
    laserScanMsg.range_max = 20.0;

    laserScanMsg.ranges.resize(scan_data_ptr->vailtidy_point_num);
    laserScanMsg.intensities.resize(scan_data_ptr->vailtidy_point_num);

    // Populate the range and intensity values from the lidar data
    for (int i = 0; i < scan_data_ptr->vailtidy_point_num; i++) {
      laserScanMsg.ranges[i] = float(scan_data_ptr->data[i].distance)/1000;
      laserScanMsg.intensities[i] = float(scan_data_ptr->data[i].intensity)/1000;
    }

    // Publish the laser scan message
    publisher_->publish(laserScanMsg);

    // Print the angles and the number of points
    RCLCPP_INFO(this->get_logger(), "Number of points: %d", scan_data_ptr->vailtidy_point_num);
    RCLCPP_INFO(this->get_logger(), "Angles: %f, %f, %f", laserScanMsg.angle_min, laserScanMsg.angle_max, laserScanMsg.angle_increment); 

    // Print the angles in the lidar data
    //for (int i = 0; i < scan_data_ptr->vailtidy_point_num; i++) {
    //  RCLCPP_INFO(this->get_logger(), "Distance[%d]: %f", i, scan_data_ptr->data[i].distance);
    //  RCLCPP_INFO(this->get_logger(), "Angle[%d]: %f", i, scan_data_ptr->data[i].angle);
    //}
  }

  ~LidarNode() {
    RCLCPP_INFO(this->get_logger(), "Shutting down");
    if (! udpThread_) {
      udpThread_->join();
    }
    close(sockFd_);
  }

private:
  int udpPort_;
  std::thread *udpThread_ =  nullptr;
  rclcpp::Publisher<sensor_msgs::msg::LaserScan>::SharedPtr publisher_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<LidarNode>();

  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
