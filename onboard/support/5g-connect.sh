#!/bin/bash

# Step 1: Get the modem number
MODEM_INFO=$(mmcli -L | grep Modem)
MODEM_NUM=$(echo "$MODEM_INFO" | grep -oP '/Modem/\K[0-9]+')

if [ -z "$MODEM_NUM" ]; then
    echo "Modem not found."
    exit 1
fi

echo "Found modem number: $MODEM_NUM"

# Step 2: Connect to the modem
echo "Connecting to the modem..."
CONNECT_OUTPUT=$(mmcli -m "$MODEM_NUM" --simple-connect="apn=bmelpg.vke,ip-type=ipv4" 2>&1)

if echo "$CONNECT_OUTPUT" | grep -q "successfully connected the modem"; then
    echo "Modem successfully connected."
else
    echo "Failed to connect the modem:"
    echo "$CONNECT_OUTPUT"
    exit 1
fi

BEARER_NUM=$(mmcli -m "$MODEM_NUM" | grep -oP 'Bearer/\K\d+')

# Step 3: Get bearer info to extract the IP address
BEARER_INFO=$(mmcli -m "$MODEM_NUM" --bearer="$BEARER_NUM")

IP_BLOCK=$(echo "$BEARER_INFO" | awk '
  /IPv4 configuration/ { in_block=1; print; next }
  in_block {
    if (/^  [^ ]/) { exit }  # A new top-level section starts
    print
  }
')
IP_ADDRESS=$(echo "$IP_BLOCK" | grep -oP 'address:\s*\K[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+')

if [ -z "$IP_ADDRESS" ]; then
    echo "Failed to retrieve IP address."
    exit 1
fi

echo "Retrieved IP address: $IP_ADDRESS"

# Step 4: Configure the network interface
echo "Configuring interface wwan0..."
ip addr add "$IP_ADDRESS"/32 dev wwan0
ip link set dev wwan0 arp off
ip link set dev wwan0 mtu 1280
ip link set wwan0 up
ip route add 10.6.6.0/24 dev wwan0

echo "Network interface wwan0 configured."
