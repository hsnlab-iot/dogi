#include "ord_lidar_driver.h"
#include "filters/FullScanFilter.h"

#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

using namespace std;
using namespace ordlidar;

unsigned char running = 1;
static void sig_handle(int signo)
{
    printf("program exit, [%s,%s] Receive SIGNAL %d ====== \r\n", __FILE__, __func__, signo);
    running = 0;
    delay(1000);
    exit(1);
}

int main(int argc, char *argv[])
{
    const char* usbPort = "/dev/ttyUSB0"; // default USB port
    const char* udpAddress = NULL; // UDP destination address
    const char* udpPort = NULL; // UDP destination port

    int opt;
    while ((opt = getopt(argc, argv, "i:u:p:h")) != -1) {
        switch (opt) {
        case 'i':
            usbPort = optarg;
            break;
        case 'u':
            udpAddress = optarg;
            break;
        case 'p':
            udpPort = optarg;
            break;
        case 'h':
            printf("Usage: %s [-i usbPort] [-a udpAddress] [-p udpPort]\n", argv[0]);
            printf("Options:\n");
            printf("  -i usbPort      Set the USB port (default: /dev/ttyUSB0)\n");
            printf("  -u udpAddress   Set the UDP destination address\n");
            printf("  -p udpPort      Set the UDP destination port\n");
            printf("  -h              Print this help message\n");
            exit(EXIT_SUCCESS);
        default: /* '?' */
            fprintf(stderr, "Usage: %s [-i usbPort] [-a udpAddress] [-p udpPort]\n", argv[0]);
            exit(EXIT_FAILURE);
        }
    }

    if (udpAddress == NULL || udpPort == NULL) {
        fprintf(stderr, "UDP destination address and port are required\n");
        exit(EXIT_FAILURE);
    }

    // Create UDP socket
    int udpSocket = socket(AF_INET, SOCK_DGRAM, 0);
    if (udpSocket < 0) {
        perror("Failed to create UDP socket");
        exit(EXIT_FAILURE);
    }

    // Set destination address and port
    struct sockaddr_in destAddr;
    memset(&destAddr, 0, sizeof(destAddr));
    destAddr.sin_family = AF_INET;
    destAddr.sin_port = htons(atoi(udpPort));
    if (inet_aton(udpAddress, &destAddr.sin_addr) == 0) {
        fprintf(stderr, "Invalid UDP destination address\n");
        exit(EXIT_FAILURE);
    }

    signal(SIGINT, sig_handle);

    uint8_t type = ORADAR_TYPE_SERIAL;
    int model = ORADAR_MS200;

    OrdlidarDriver device(type, model);
    full_scan_data_st scan_data, out_data;
    
    int serialBaudrate = 230400;
    bool is_logging = false;
    bool ret = false;
    long long count = 0;
    device.SetSerialPort(usbPort, serialBaudrate);

    while (running)
    {
        if (device.Connect())
        {
            printf("scan_frame_data lidar device connect succuss..\n");
            // Get device information
            std::string sn;
            std::string firmwareVersion;
            std::string topFirmwareVersion;
            std::string botFirmwareVersion;
            double rotationSpeed;
            if (device.GetDeviceSN(sn) && device.GetFirmwareVersion(topFirmwareVersion, botFirmwareVersion)) {
                firmwareVersion = topFirmwareVersion + " / " + botFirmwareVersion;
                printf("Serial Number: %s\n", sn.c_str());
                printf("Firmware Version: %s\n", firmwareVersion.c_str());
                printf("Rotation Speed: %f\n", device.GetRotationSpeed());
            } else {
                printf("Failed to get device information\n");
            }
            break;
        }
        else
        {
            printf("lidar device connect %s fail..\n", usbPort);
            delay(1000);
        }
    }

    FullScanFilter filter;
    FilterPara para;
    para.filter_type = FullScanFilter::FS_Intensity;
    while (running)
    {
        ret = device.GrabFullScanBlocking(scan_data, 1000);
        if (ret)
        {
            printf("count = %lld, point_num: %d\n", ++count, scan_data.vailtidy_point_num);
            //filter.filter(scan_data, para, out_data);
            if (is_logging)
            {
                for (int i = 0; i < scan_data.vailtidy_point_num; i++)
                {
                    printf("[%d: %f, %f] \n", i, (scan_data.data[i].distance * 0.001), scan_data.data[i].angle);
                }
            }
            // Send data over UDP
            ssize_t numBytesSent = sendto(udpSocket, &scan_data, scan_data.vailtidy_point_num * sizeof(point_data_t), 0, (struct sockaddr*)&destAddr, sizeof(destAddr));
            if (numBytesSent < 0) {
                perror("Failed to send data over UDP");
                //exit(EXIT_FAILURE);
            }
        }
        else
        {
            printf("error: fail get full scan data\n");
        }
    }

exit:
    device.Disconnect();

    // Close UDP socket
    close(udpSocket);

    return 0;
}