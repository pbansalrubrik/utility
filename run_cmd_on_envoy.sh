#!/bin/bash

# This script executes a given command on multiple SSH ports.
# It uses the provided SSH key and a fixed IP address (127.128.0.1).

# Define the SSH key path and username
SSH_KEY="/var/lib/rubrik/certs/envoy_ng/envoy_ng_ssh.pem"
SSH_USER="ubuntu"
SSH_HOST="127.128.0.1"

# Fetch the list of ports dynamically from envoy_config table
PORTS=($(cqlsh -k sd -e "select ssh_pfp_assignment from envoy_config" \
  2>/dev/null | grep -E '^\s*[0-9]+\s*$' | tr -d ' '))

# Check if we got any ports
if [ ${#PORTS[@]} -eq 0 ]; then
  echo "Error: Could not fetch ports from envoy_config table."
  echo "Make sure cqlsh is available and the database is accessible."
  exit 1
fi

# Function to copy a file to all envoys
copy_file() {
  local source_path="$1"
  local dest_path="$2"

  # Validate arguments
  if [ -z "$source_path" ] || [ -z "$dest_path" ]; then
    echo "Error: Both source and destination paths are required."
    echo "Usage: $0 copy_file <source_path> <destination_path>"
    return 1
  fi

  # Check if source file exists
  if [ ! -f "$source_path" ]; then
    echo "Error: Source file '$source_path' does not exist."
    return 1
  fi

  echo "Copying '$source_path' to '$dest_path' on all envoys..."
  echo "-------------------------------------------------------------------"

  local success_count=0
  local fail_count=0

  # Loop through each port and copy the file
  for PORT in "${PORTS[@]}"; do
    echo "--- Copying to envoy on port: $PORT ---"
    if sudo scp -i "$SSH_KEY" -P "$PORT" "$source_path" "$SSH_USER@$SSH_HOST:$dest_path" 2>&1; then
      echo "Success"
      success_count=$((success_count + 1))
    else
      echo "Failed to copy"
      fail_count=$((fail_count + 1))
    fi
    echo "-------------------------------------------------------------------"
  done

  echo ""
  echo "SUMMARY:"
  echo "========"
  echo "Successfully copied to: $success_count envoy(s)"
  if [ $fail_count -gt 0 ]; then
    echo "Failed to copy to: $fail_count envoy(s)"
  fi

  return $fail_count
}

# Function to count connections on port 902
count_902_connections() {
  local total_connections=0
  local temp_file=$(mktemp)
  local all_connections_file=$(mktemp)

  echo "Checking connections on port 902 across all envoys..."
  echo "-------------------------------------------------------------------"

  # Loop through each port and collect connection data
  for PORT in "${PORTS[@]}"; do
    echo "--- Checking port: $PORT ---"

    # Run the netstat command and capture output
    if sudo ssh -i "$SSH_KEY" "$SSH_USER@$SSH_HOST" -p "$PORT" "netstat -an | grep -w 902" 2>/dev/null > "$temp_file"; then
      local connections=$(wc -l < "$temp_file")
      if [ "$connections" -gt 0 ]; then
        echo "Found $connections connection(s):"
        cat "$temp_file"
        # Append all connections to the master file for aggregation
        cat "$temp_file" >> "$all_connections_file"
        total_connections=$((total_connections + connections))
      else
        echo "No connections found"
      fi
    else
      echo "Failed to connect or no connections found"
    fi
    echo "-------------------------------------------------------------------"
  done

  echo ""
  echo "SUMMARY:"
  echo "========"
  echo "Total connections on port 902 across all envoys: $total_connections"

  # Parse and aggregate connections per IP
  if [ -s "$all_connections_file" ]; then
    echo ""
    echo "CONNECTIONS PER IP:"
    echo "==================="
    # Extract the remote IP from netstat output (field with :902) and count occurrences
    # netstat format: tcp 0 0 local_ip:port remote_ip:902 STATE
    awk '{
      # Find the field that ends with :902
      for(i=1; i<=NF; i++) {
        if($i ~ /:902$/) {
          # Extract IP by removing :902
          ip = $i
          gsub(/:902$/, "", ip)
          count[ip]++
          break
        }
      }
    }
    END {
      for(ip in count) {
        printf "%d %s\n", count[ip], ip
      }
    }' "$all_connections_file" | sort -nr
  fi

  # Cleanup
  rm -f "$temp_file" "$all_connections_file"

  return $total_connections
}

# Check if a command was provided as an argument
if [ -z "$1" ]; then
  echo "Usage: $0 \"<command_to_run>\""
  echo "Example: $0 \"systemctl status vddk | grep Active\""
  echo ""
  echo "Special commands:"
  echo "  $0 \"count-902\"              - Count all connections on port 902 (single run)"
  echo "  $0 \"count-902\" \"continuous\"  - Monitor port 902 connections every minute and log to file"
  echo "  $0 copy_file <source> <dest> - Copy a file from this machine to all envoys"
  exit 1
fi

# Check for copy_file command
if [ "$1" = "copy_file" ]; then
  copy_file "$2" "$3"
  exit $?
fi

# Check for special command to count 902 connections
if [ "$1" = "count-902" ]; then
  # Check if continuous monitoring is requested
  if [ "$2" = "continuous" ]; then
    # Generate log filename with timestamp (compact format for filename)
    LOG_FILE="envoy_902_connections_$(date +%Y%m%d_%H%M%S).txt"
    echo "Starting continuous monitoring of port 902 connections..."
    echo "Logging to: $LOG_FILE"
    echo "Press Ctrl+C to stop monitoring"
    echo ""

    # Add header to log file (ISO 8601 format inside log)
    echo "=== Envoy Port 902 Connection Monitor Started at $(date +%Y-%m-%dT%H:%M:%S) ===" > "$LOG_FILE"
    echo "" >> "$LOG_FILE"

    # Continuous loop
    while true; do
      echo "=== $(date +%Y-%m-%dT%H:%M:%S) ===" | tee -a "$LOG_FILE"
      count_902_connections | tee -a "$LOG_FILE"
      echo "" | tee -a "$LOG_FILE"
      echo "Waiting 60 seconds... (Press Ctrl+C to stop)"
      sleep 60
    done
  else
    # Single run mode
    count_902_connections
  fi
  exit 0
fi

# Store the command provided by the user
COMMAND_TO_RUN="$@"

echo "Attempting to run command: \"$COMMAND_TO_RUN\" on ports: ${PORTS[@]}"
echo "-------------------------------------------------------------------"

# Loop through each port and execute the command
for PORT in "${PORTS[@]}"; do
  echo "--- Running on port: $PORT ---"
  # Construct and execute the SSH command
  # The 'eval' command is used here to correctly handle the COMMAND_TO_RUN
  # which might contain pipes or other shell special characters.
  # Be cautious with 'eval' if the input command is untrusted, but for
  # internal use with known commands, it's appropriate.
  eval "sudo ssh -i \"$SSH_KEY\" \"$SSH_USER@$SSH_HOST\" -p \"$PORT\" \"$COMMAND_TO_RUN\""
  echo "-------------------------------------------------------------------"
done

echo "Script execution complete"
