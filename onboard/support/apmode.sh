#!/bin/bash

# PERMISSION CHECK: Check if the effective User ID is 0 (root)
if [ "$EUID" -ne 0 ]; then
    echo "--------------------------------------------------------"
    echo "ERROR: Permission Denied."
    echo "This script modifies hardware and firewall rules."
    echo "Please run with: sudo $0"
    echo "--------------------------------------------------------"
    exit 1
fi

# Check if the DogiFallbackAP is already the active connection
CURRENT_CON=$(nmcli -t -f GENERAL.CONNECTION device show wlan0 | head -n 1 | awk -F: '{print $2}')

# SMART WIFI SWITCH: Only initiate 'up' if not already active
if [ "$CURRENT_CON" != "DogiFallbackAP" ]; then
    echo "Dogi: Not on DogiFallbackAP (Current: $CURRENT_CON). Initiating switch..."
    nmcli conn up DogiFallbackAP
else
    echo "Dogi: Already on DogiFallbackAP. Skipping WiFi re-connect."
fi

# Enable forward
sysctl -w net.ipv4.ip_forward=1

# NAT Masquerade
if ! iptables -t nat -C POSTROUTING -o wwan0 -j MASQUERADE 2>/dev/null; then
    iptables -t nat -A POSTROUTING -o wwan0 -j MASQUERADE
    echo "  + Added NAT Masquerade"
fi

# Forwarding: WiFi -> 5G
if ! iptables -C FORWARD -i wlan0 -o wwan0 -j ACCEPT 2>/dev/null; then
    iptables -A FORWARD -i wlan0 -o wwan0 -j ACCEPT
    echo "  + Added Forwarding (WiFi -> 5G)"
fi

# Forwarding: 5G -> WiFi
if ! iptables -C FORWARD -i wwan0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; then
    iptables -A FORWARD -i wwan0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT
    echo "  + Added Forwarding (5G -> WiFi)"
fi

echo "Dogi: AP Mode and 5G Bridge are verified and ACTIVE."
