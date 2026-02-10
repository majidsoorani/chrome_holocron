#!/bin/sh
TARGET="8.8.8.8"

echo "======================================================================"
echo " Modem Performance Monitor"
echo " Target: $TARGET"
echo " Press Ctrl+C to Stop"
echo "======================================================================"
printf "%-10s | %-15s | %-15s | %-15s\n" "Time" "Zitel (wan)" "Irancell (wl1)" "RighTel (lan3)"
echo "----------------------------------------------------------------------"

while true; do
    TIME=$(date +%H:%M:%S)
    
    # --- Zitel (wan) ---
    # Ping with 10s timeout, 1 packet
    PING_Z=$(ping -c 1 -W 10 -I wan $TARGET 2>/dev/null)
    if [ $? -eq 0 ]; then
        # Extract avg latency
        LAT_Z=$(echo "$PING_Z" | awk -F'/' '/round-trip/ {print $4}')
        if [ -z "$LAT_Z" ]; then LAT_Z=$(echo "$PING_Z" | awk -F'/' '/rtt/ {print $4}'); fi # Busybox ping sometimes uses rtt
        STAT_Z="${LAT_Z}ms"
    else
        STAT_Z="LOSS"
    fi

    # --- Irancell (wl1-sta0) ---
    PING_I=$(ping -c 1 -W 10 -I wl1-sta0 $TARGET 2>/dev/null)
    if [ $? -eq 0 ]; then
        LAT_I=$(echo "$PING_I" | awk -F'/' '/round-trip/ {print $4}')
        if [ -z "$LAT_I" ]; then LAT_I=$(echo "$PING_I" | awk -F'/' '/rtt/ {print $4}'); fi
        STAT_I="${LAT_I}ms"
    else
        STAT_I="LOSS"
    fi

    # --- RighTel (lan3) ---
    # Only check if interface is administratively UP
    if ip link show lan3 2>/dev/null | grep -q "UP"; then
        PING_R=$(ping -c 1 -W 10 -I lan3 $TARGET 2>/dev/null)
        if [ $? -eq 0 ]; then
             LAT_R=$(echo "$PING_R" | awk -F'/' '/round-trip/ {print $4}')
             if [ -z "$LAT_R" ]; then LAT_R=$(echo "$PING_R" | awk -F'/' '/rtt/ {print $4}'); fi
             STAT_R="${LAT_R}ms"
        else
             STAT_R="LOSS"
        fi
    else
        STAT_R="DOWN"
    fi

    printf "%-10s | %-15s | %-15s | %-15s\n" "$TIME" "$STAT_Z" "$STAT_I" "$STAT_R"
    sleep 1
done
