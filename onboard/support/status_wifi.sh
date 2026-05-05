#!/bin/sh
# Output one of: MODE:AP, MODE:STA, MODE:OFF

if command -v iw >/dev/null 2>&1; then
    IW_OUT="$(iw dev 2>/dev/null)"
    echo "$IW_OUT" | grep -q "type AP" && {
        echo "MODE:AP"
        exit 0
    }
    echo "$IW_OUT" | grep -q "type managed" && {
        echo "MODE:STA"
        exit 0
    }
fi

if command -v nmcli >/dev/null 2>&1; then
    NM_OUT="$(nmcli -t -f DEVICE,TYPE,STATE dev 2>/dev/null)"
    echo "$NM_OUT" | awk -F: '$2=="wifi" && ($3=="connected" || $3=="connecting") {found=1} END {if (found) print "MODE:STA"}' | grep -q "MODE:STA"
    if [ $? -eq 0 ]; then
        echo "MODE:STA"
        exit 0
    fi
fi

echo "MODE:OFF"
