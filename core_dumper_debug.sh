#!/bin/bash
# Simplified core dumper - writes unencrypted gzip to /var/crash
LOG_FILE="/var/log/core_dumper.log"
log() {
  echo "$(date -Ins) $@" >> "$LOG_FILE"
}

if [ "$#" -lt 5 ]; then
  log "Usage: $0 timestamp pid executable_name core_size signal"
  exit 1
fi

FOLDER="/var/crash/$3"
mkdir -p "$FOLDER"
CORE_PATH="$FOLDER/$1.$2.$3.core.gz"
log "Writing unencrypted core dump to $CORE_PATH"
gzip -c > "$CORE_PATH"
log "Done writing $CORE_PATH"
