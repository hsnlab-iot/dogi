#!/bin/sh
# Output format: wlan0:<IPv4|N/A>|wwan0:<IPv4|N/A>

get_ipv4() {
    IFACE="$1"
    IP_ADDR="$(ip -4 -o addr show "$IFACE" 2>/dev/null | awk '{print $4}' | head -n1 | cut -d/ -f1)"
    if [ -n "$IP_ADDR" ]; then
        echo "$IP_ADDR"
    else
        echo "N/A"
    fi
}

WLAN_IP="$(get_ipv4 wlan0)"
WWAN_IP="$(get_ipv4 wwan0)"

echo "wlan0:${WLAN_IP}|wwan0:${WWAN_IP}"
