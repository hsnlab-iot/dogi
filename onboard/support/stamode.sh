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

PREFERRED_SSID="preconfigured"

# Force Hardware Disconnect
nmcli device disconnect wlan0 > /dev/null 2>&1
sleep 1

# Cleanup Firewall
iptables -t nat -D POSTROUTING -o wwan0 -j MASQUERADE 2>/dev/null
iptables -D FORWARD -i wlan0 -o wwan0 -j ACCEPT 2>/dev/null
iptables -D FORWARD -i wwan0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null

# Reset Radio State
nmcli radio wifi off
sleep 1
nmcli radio wifi on
sleep 1

# ATTEMPT TARGETED CONNECTION
echo "Dogi: Attempting to force connection to '$PREFERRED_SSID'..."
if nmcli connection up id "$PREFERRED_SSID"; then
    echo "Dogi: SUCCESS! Connected to Preferred Network: $PREFERRED_SSID"
else
    echo "Dogi: '$PREFERRED_SSID' not found. Falling back to Priority Autoconnect..."
    nmcli device set wlan0 autoconnect yes
    if nmcli device connect wlan0; then
        ACTIVE=$(nmcli -t -f active,ssid dev wifi | grep '^yes' | cut -d: -f2)
        echo "Dogi: Connected to fallback: $ACTIVE"
    else
        echo "Dogi: CRITICAL - No known networks found."
    fi
fi

echo "Dogi: Station Mode Script Finished."
