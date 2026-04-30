#!/bin/bash

# This script executes a given command on all SSF stress-test SSH tunnels.
# It discovers active stress tunnel ports from ssfd's listening sockets.

SSH_KEY="/var/lib/rubrik/certs/envoy_ng/envoy_ng_ssh.pem"
SSH_USER="ubuntu"
SSH_HOST="127.128.0.1"

action="${1:-}"

if [ "$action" = "list" ]; then
  echo "Discovering SSF stress tunnel ports (40001+)..."
  PORTS=$(netstat -tlnp 2>/dev/null | grep ssfd | awk '{print $4}' | grep -oP '(?<=:)4\d{4}$' | sort -n)
  if [ -z "$PORTS" ]; then
    echo "No stress tunnel ports found."
  else
    echo "Active ports:"
    echo "$PORTS"
    echo "Count: $(echo "$PORTS" | wc -l)"
  fi
  exit 0
fi

if [ -z "$action" ]; then
  echo "Usage:"
  echo "  $0 list                      - list all active stress tunnel ports"
  echo "  $0 \"<command>\"               - run command on all stress tunnels"
  echo "  $0 \"<command>\" <port>        - run command on a specific port"
  echo ""
  echo "Examples:"
  echo "  $0 list"
  echo "  $0 \"hostname\""
  echo "  $0 \"systemctl status sshd\" 40001"
  exit 1
fi

COMMAND_TO_RUN="$1"
SPECIFIC_PORT="$2"

if [ -n "$SPECIFIC_PORT" ]; then
  PORTS=("$SPECIFIC_PORT")
else
  mapfile -t PORTS < <(netstat -tlnp 2>/dev/null | grep ssfd | awk '{print $4}' | grep -oP '(?<=:)4\d{4}$' | sort -n)
fi

if [ ${#PORTS[@]} -eq 0 ]; then
  echo "No stress tunnel ports found. Are the stress SSF clients running?"
  exit 1
fi

echo "Running: \"$COMMAND_TO_RUN\" on ${#PORTS[@]} port(s): ${PORTS[*]}"
echo "-------------------------------------------------------------------"

for PORT in "${PORTS[@]}"; do
  echo "--- Port: $PORT ---"
  sudo ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no \
    -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" -p "$PORT" "$COMMAND_TO_RUN" 2>&1
  echo "-------------------------------------------------------------------"
done

echo "Done. Ran on ${#PORTS[@]} port(s)."
