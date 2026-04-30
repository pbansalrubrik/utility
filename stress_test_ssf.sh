#!/bin/bash
# Spin up N SSF client background processes for stress testing.
# Usage: sudo bash stress_test_ssf.sh [start|stop|clean] [num_instances (default 10)] [cdm_node_ip]
#
# Each instance gets a copy of ForwardUserServiceConfig_all_nodes.json
# with port 33804 replaced by a unique port (base 40000 + i).

set -euo pipefail

SERVER_IP="10.0.x86.1223"
SERVER_PORT="8011"
BASE_PORT=40000
TEMPLATE_FORWARD="/home/ubuntu/envoy_configs/ForwardUserServiceConfig_all_nodes.json"
TEMPLATE_REVERSE="/home/ubuntu/envoy_configs/ReverseUserServiceConfig_B-1495-lb.json"
CONFIG_DIR="/home/ubuntu/envoy_configs"
PID_DIR="/tmp/ssf_stress_pids"
STRESS_CFG_DIR="${CONFIG_DIR}/stress"

action="${1:-start}"
NUM_INSTANCES="${2:-10}"
SERVER_IP="${3:-$SERVER_IP}"

case "$action" in
  start)
    if [ ! -f "$TEMPLATE_FORWARD" ]; then
      echo "ERROR: Template forward config not found: $TEMPLATE_FORWARD"
      exit 1
    fi

    mkdir -p "$PID_DIR" "$STRESS_CFG_DIR"

    echo "Launching $NUM_INSTANCES SSF client instances..."
    for i in $(seq 1 $NUM_INSTANCES); do
      NODE_UUID="stress-$(printf '%03d' $i)"
      LOCAL_PORT=$((BASE_PORT + i))
      FORWARD_CFG="${STRESS_CFG_DIR}/ForwardUserServiceConfig_${NODE_UUID}.json"
      REVERSE_CFG="${STRESS_CFG_DIR}/ReverseUserServiceConfig_${NODE_UUID}.json"
      LOG_DIR="/var/log/ssf-${NODE_UUID}"

      # Generate forward config with single SSH rule using unique port
      cat > "$FORWARD_CFG" <<EOF
{
  "127.128.0.1:${LOCAL_PORT}:127.128.0.1:22": "R"
}
EOF

      # Generate reverse config with unique port for 443 forwarding
      REVERSE_PORT=$((BASE_PORT + i))
      cat > "$REVERSE_CFG" <<EOF
{
  "127.128.0.2:${REVERSE_PORT}:127.128.0.2:443": "L"
}
EOF

      mkdir -p "$LOG_DIR"
      chown -R ubuntu:ubuntu "$LOG_DIR"

      /opt/ssf/ssf "$SERVER_IP" -p "$SERVER_PORT" \
        -v debug -c /opt/ssf/ssf_config.json -g \
        -k "$FORWARD_CFG" \
        -b "$REVERSE_CFG" \
        -m 3 \
        -y "$NODE_UUID" \
        > "$LOG_DIR/ssf.log" 2>&1 &

      echo $! > "${PID_DIR}/${NODE_UUID}.pid"
      echo "  Started ${NODE_UUID} (PID: $!) port ${LOCAL_PORT}"
    done

    echo ""
    echo "Done. $NUM_INSTANCES instances launched (SSH ports $((BASE_PORT+1)) to $((BASE_PORT+NUM_INSTANCES)))."
    echo "Status: sudo bash $0 status"
    echo "Stop:   sudo bash $0 stop"
    ;;

  stop)
    echo "Killing all stress-test SSF instances..."
    # Find all stress SSF processes by command line and kill them
    pids=$(ps -ef | grep '[s]sf.*-y stress-' | awk '{print $2}')
    if [ -n "$pids" ]; then
      count=$(echo "$pids" | wc -w)
      echo "$pids" | xargs kill -9
      echo "  Killed $count processes"
    else
      echo "  No stress SSF processes found"
    fi
    rm -rf "$PID_DIR"
    rm -rf "$STRESS_CFG_DIR"
    echo "All stress instances stopped."
    ;;

  clean)
    echo "Stopping and cleaning up..."
    bash "$0" stop

    for i in $(seq 1 $NUM_INSTANCES); do
      NODE_UUID="stress-$(printf '%03d' $i)"
      rm -rf "/var/log/ssf-${NODE_UUID}"
    done
    rm -rf "$STRESS_CFG_DIR"
    rm -rf "$PID_DIR"
    echo "Cleanup complete."
    ;;

  status)
    echo "Stress SSF client memory usage:"
    echo "-------------------------------------------------------------------"
    printf "%-12s %-10s %s\n" "UUID" "PID" "RSS (MB)"
    echo "-------------------------------------------------------------------"
    total_rss=0
    count=0
    while read -r pid; do
      uuid=$(ps -o args= -p "$pid" 2>/dev/null | grep -oP '(?<=-y )\S+')
      rss=$(ps -o rss= -p "$pid" 2>/dev/null | tr -d ' ')
      if [ -n "$rss" ] && [ "$rss" -gt 0 ]; then
        mb=$((rss / 1024))
        printf "%-12s %-10s %s\n" "$uuid" "$pid" "$mb"
        total_rss=$((total_rss + rss))
        count=$((count + 1))
      fi
    done < <(ps -ef | grep '[s]sf.*-y stress-' | awk '{print $2}')
    total_mb=$((total_rss / 1024))
    avg_mb=0
    if [ "$count" -gt 0 ]; then
      avg_mb=$((total_mb / count))
    fi
    echo "-------------------------------------------------------------------"
    echo "Total: ${count} processes, ${total_mb} MB, avg ${avg_mb} MB/process"
    ;;

  *)
    echo "Usage: sudo bash $0 [start|stop|clean|status] [num_instances (default 10)] [cdm_node_ip (default 10.0.86.120)]"
    exit 1
    ;;
esac
