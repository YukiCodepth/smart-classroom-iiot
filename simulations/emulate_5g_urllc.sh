#!/usr/bin/env bash
# ==============================================================================
# 5G URLLC (Ultra-Reliable Low-Latency Communication) Network Emulation Script
# Leverages Linux Kernel Traffic Control (tc / netem) to simulate 5G RAN delays
# ==============================================================================

INTERFACE="lo"  # Loopback interface where local Docker sockets communicate
DELAY="3ms"     # 5G URLLC average uplink/downlink latency
JITTER="1ms"    # Natural cellular radio jitter
LOSS="0.01%"    # Micro-packet drop rate over cellular air interfaces

case "$1" in
    start)
        echo "[INFO] Injecting 5G URLLC Radio Emulation onto interface [$INTERFACE]..."
        sudo tc qdisc add dev $INTERFACE root netem delay $DELAY $JITTER loss $LOSS
        echo "[SUCCESS] Active 5G Emulation Profile: Latency=$DELAY ±$JITTER | Packet Loss=$LOSS"
        ;;
    stop)
        echo "[INFO] Removing 5G RAN Emulation from interface [$INTERFACE]..."
        sudo tc qdisc del dev $INTERFACE root netem 2>/dev/null || echo "[WARN] No active emulation found to remove."
        echo "[SUCCESS] Network interface restored to bare-metal local speeds."
        ;;
    status)
        echo "=== CURRENT KERNEL TRAFFIC CONTROL STATUS ($INTERFACE) ==="
        tc qdisc show dev $INTERFACE
        ;;
    *)
        echo "Usage: $0 {start|stop|status}"
        exit 1
        ;;
esac
