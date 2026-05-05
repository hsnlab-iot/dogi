#!/bin/sh
# Evaluate wg0/wg1 and output route preference.
# wg0 has IP and wg1 does not -> ROUTE:WIFI
# wg1 has IP and wg0 does not -> ROUTE:5G
# otherwise -> ROUTE:UNKNOWN

has_ipv4() {
    IFACE="$1"
    ip -4 -o addr show "$IFACE" 2>/dev/null | awk 'NR==1 { if ($4 != "") print "yes" }'
}

WG0_HAS="$(has_ipv4 wg0)"
WG1_HAS="$(has_ipv4 wg1)"

if [ "$WG0_HAS" = "yes" ] && [ "$WG1_HAS" != "yes" ]; then
    echo "ROUTE:WIFI"
elif [ "$WG1_HAS" = "yes" ] && [ "$WG0_HAS" != "yes" ]; then
    echo "ROUTE:5G"
else
    echo "ROUTE:UNKNOWN"
fi
