#!/bin/sh
TARGET="34.244.201.246"

echo "======================================================================"
echo " Modem Performance Monitor (TCP/22)"
echo " Target: $TARGET"
echo " Press Ctrl+C to Stop"
echo "======================================================================"
printf "%-10s | %-15s | %-15s | %-15s | %-10s\n" "Time" "Zitel (wan)" "Irancell (wl1)" "RighTel (lan3)" "Best"
echo "----------------------------------------------------------------------"

while true; do
    TIME=$(date +%H:%M:%S)
    
    # --- Zitel (wan) ---
    # TCP Check using curl (HTTP/0.9 to port 22)
    CURL_Z=$(curl -o /dev/null -s -w "%{time_starttransfer}" --http0.9 --connect-timeout 2 --interface wan http://$TARGET:22 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$CURL_Z" ] && [ "$CURL_Z" != "0.000000" ]; then
        # Convert seconds to ms (float to int)
        VAL_Z=$(awk -v t="$CURL_Z" 'BEGIN {printf "%.0f", t * 1000}')
        STAT_Z="${VAL_Z}ms"
    else
        STAT_Z="LOSS"
        VAL_Z=9999
    fi

    # --- Irancell (wl1-sta0) ---
    CURL_I=$(curl -o /dev/null -s -w "%{time_starttransfer}" --http0.9 --connect-timeout 2 --interface wl1-sta0 http://$TARGET:22 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$CURL_I" ] && [ "$CURL_I" != "0.000000" ]; then
        VAL_I=$(awk -v t="$CURL_I" 'BEGIN {printf "%.0f", t * 1000}')
        STAT_I="${VAL_I}ms"
    else
        STAT_I="LOSS"
        VAL_I=9999
    fi

    # --- RighTel (lan3) ---
    if ip link show lan3 2>/dev/null | grep -q "UP"; then
        CURL_R=$(curl -o /dev/null -s -w "%{time_starttransfer}" --http0.9 --connect-timeout 2 --interface lan3 http://$TARGET:22 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$CURL_R" ] && [ "$CURL_R" != "0.000000" ]; then
             VAL_R=$(awk -v t="$CURL_R" 'BEGIN {printf "%.0f", t * 1000}')
             STAT_R="${VAL_R}ms"
        else
             STAT_R="LOSS"
             VAL_R=9999
        fi
    else
        STAT_R="DOWN"
        VAL_R=9999
    fi

    # Determine Best
    BEST="NONE"
    MIN_VAL=9998

    if [ "$VAL_Z" -lt "$MIN_VAL" ]; then
        MIN_VAL=$VAL_Z
        BEST="Zitel"
    fi
    if [ "$VAL_I" -lt "$MIN_VAL" ]; then
        MIN_VAL=$VAL_I
        BEST="Irancell"
    fi
    if [ "$VAL_R" -lt "$MIN_VAL" ]; then
        MIN_VAL=$VAL_R
        BEST="RighTel"
    fi

    printf "%-10s | %-15s | %-15s | %-15s | %-10s\n" "$TIME" "$STAT_Z" "$STAT_I" "$STAT_R" "$BEST"
    sleep 1
done
