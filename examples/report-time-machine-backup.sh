#!/bin/bash
# Run on the Mac that makes the backup. See README for setup.
set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "Usage: $0 <backup volume mount point> <Home Assistant webhook URL>" >&2
    exit 2
fi

backup_volume=$1
webhook_url=$2
if [[ ! -d "$backup_volume" ]] || ! /sbin/mount | /usr/bin/grep -F -- " on $backup_volume (" >/dev/null; then
    echo "The Time Machine destination is not mounted at $backup_volume." >&2
    exit 1
fi

# The explicit destination keeps a backup on a different disk from refreshing this sensor.
backup=$(/usr/bin/tmutil latestbackup -d "$backup_volume" -t)
# Some versions return a path despite -t. Accept the timestamp in either form.
if [[ ! "$backup" =~ ([0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{6})([.]backup)?/?$ ]]; then
    echo "Could not read a completed Time Machine backup timestamp." >&2
    exit 1
fi
timestamp=$(/bin/date -j -f '%Y-%m-%d-%H%M%S' "${BASH_REMATCH[1]}" '+%Y-%m-%dT%H:%M:%S%z')
/usr/bin/curl --fail --silent --show-error --max-time 15 \
    --header 'Content-Type: application/json' \
    --data "{\"backup_at\":\"$timestamp\"}" \
    -- "$webhook_url"
