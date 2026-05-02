#!/bin/bash
# Monthly refresh wrapper for the US Generation map.
# Invoked by launchd (~/Library/LaunchAgents/com.gaiergy.update-generation-map.plist).
# Reruns build_map.py against the latest EIA-860M, captures a summary, and
# posts a macOS notification. Wrapped in /bin/bash so it inherits Full Disk
# Access (calling /usr/bin/python3 directly from launchd hits a TCC denial
# on files under ~/Desktop).

set -u

DIR="/Users/jasonmasters/Desktop/Ground Floor Energy/Research/Site Potentials"
PY="/usr/bin/python3"
LOG="$DIR/refresh.log"
SUMMARY="$DIR/last_run_summary.txt"

cd "$DIR" || { echo "[$(date)] cd failed" >> "$LOG"; exit 1; }

{
    echo
    echo "=========================================="
    echo "[$(date)] Monthly map refresh starting"
    echo "=========================================="
} >> "$LOG"

"$PY" -u "$DIR/build_map.py" >> "$LOG" 2>&1
RC=$?
echo "[$(date)] build_map.py exit code: $RC" >> "$LOG"

# Pull the most recent matches of each stats line out of the log.
PLANTS_LINE=$(grep -E "Built [0-9,]+ plants" "$LOG" | tail -1 | sed 's/^[[:space:]]*//')
WROTE_LINE=$(grep -E "Wrote map.html" "$LOG" | tail -1 | sed 's/^[[:space:]]*//')
USED_LINE=$(grep -E "Using existing|^  Saved 20[0-9][0-9]-[0-9][0-9]\.xlsx" "$LOG" | tail -1 | sed 's/^[[:space:]]*//')

{
    echo "Map refresh run: $(date '+%Y-%m-%dT%H:%M:%S%z')"
    if [[ $RC -eq 0 ]]; then
        echo "STATUS: OK"
    else
        echo "STATUS: FAILED (build_map.py exit code $RC). See refresh.log."
    fi
    [[ -n "$USED_LINE" ]] && echo "Source: $USED_LINE"
    [[ -n "$PLANTS_LINE" ]] && echo "$PLANTS_LINE"
    [[ -n "$WROTE_LINE" ]] && echo "$WROTE_LINE"
} > "$SUMMARY"

SUMMARY_TEXT="$(cat "$SUMMARY" 2>/dev/null || echo 'No summary written')"

/usr/bin/osascript -e "display notification \"$(echo "$SUMMARY_TEXT" | tr '\n' ' ' | sed 's/\"/\\\\\"/g' | cut -c1-200)\" with title \"US Generation map refresh\" subtitle \"$(date '+%Y-%m-%d %H:%M')\"" 2>/dev/null || true

echo "[$(date)] Refresh complete. Summary written to $SUMMARY" >> "$LOG"
exit $RC
