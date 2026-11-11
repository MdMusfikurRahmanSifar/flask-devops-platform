#!/usr/bin/env bash
# system_health.sh - collect system health metrics, log them, warn on thresholds.
# Exit codes: 0 = healthy, 1 = warning, 2 = critical (bad args / missing /proc)
#
# Linux-targeted (uses /proc and /proc/meminfo; validated on python:3.12-slim container).

set -euo pipefail

# ─── Defaults ────────────────────────────────────────────────────────────
DISK_THRESHOLD=80
CPU_THRESHOLD=90
MEM_THRESHOLD=85
LOG_FILE="health_log.txt"
MAX_LOG_BYTES=1048576    # rotate at 1 MiB
JSON_OUTPUT=false
QUIET=false

# ─── Help ────────────────────────────────────────────────────────────────
usage() {
  cat <<'EOF'
Collect system health metrics with threshold warnings.

Options:
  --disk N     Disk usage warning threshold % (default: 80)
  --cpu N      CPU usage warning threshold % (default: 90)
  --mem N      Memory usage warning threshold % (default: 85)
  --log FILE   Log file path (default: health_log.txt)
  --json       Emit JSON instead of plain text
  --quiet      Suppress stdout (log file only)
  -h, --help   Show this help

Exit codes: 0 = healthy, 1 = warning, 2 = critical
EOF
}

# ─── Args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --disk)  DISK_THRESHOLD="$2"; shift 2 ;;
    --cpu)   CPU_THRESHOLD="$2";  shift 2 ;;
    --mem)   MEM_THRESHOLD="$2";  shift 2 ;;
    --log)   LOG_FILE="$2";       shift 2 ;;
    --json)  JSON_OUTPUT=true;    shift ;;
    --quiet) QUIET=true;          shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -r /proc/stat ]]   || { echo "ERROR: /proc/stat not readable" >&2; exit 2; }
[[ -r /proc/meminfo ]] || { echo "ERROR: /proc/meminfo not readable" >&2; exit 2; }

# ─── Collectors ──────────────────────────────────────────────────────────
cpu_percent() {
  local u1 n1 s1 i1 io1 ir1 si1 st1
  local u2 n2 s2 i2 io2 ir2 si2 st2
  read -r _ u1 n1 s1 i1 io1 ir1 si1 st1 _ < /proc/stat
  sleep 1
  read -r _ u2 n2 s2 i2 io2 ir2 si2 st2 _ < /proc/stat
  local total1=$((u1+n1+s1+i1+io1+ir1+si1+st1))
  local total2=$((u2+n2+s2+i2+io2+ir2+si2+st2))
  local idle1=$((i1+io1))
  local idle2=$((i2+io2))
  local dt=$((total2-total1))
  local di=$((idle2-idle1))
  [[ "$dt" -le 0 ]] && { echo 0; return; }
  echo $(( 100 * (dt - di) / dt ))
}

mem_percent() {
  local total avail
  total=$(awk '/^MemTotal:/     {print $2}' /proc/meminfo)
  avail=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
  echo $(( 100 * (total - avail) / total ))
}

load_avg() {
  awk '{printf "%.2f,%.2f,%.2f", $1, $2, $3}' /proc/loadavg
}

disk_usage() {
  df -P | awk 'NR>1 && $1 !~ /^(tmpfs|devtmpfs|overlay|shm|udev)$/ && $2 > 0 {
    p = $5; sub(/%$/, "", p);
    print $6 ":" p
  }'
}

top5_procs() {
  ps -eo pid=,comm=,rss= --sort=-rss | head -5 | awk '{printf "%s:%s:%s\n", $1, $2, $3}'
}

# ─── Log rotation ────────────────────────────────────────────────────────
rotate_log() {
  [[ -f "$LOG_FILE" ]] || return 0
  local size
  size=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
  [[ "$size" -le "$MAX_LOG_BYTES" ]] && return 0
  mv "$LOG_FILE" "${LOG_FILE}.$(date +%Y%m%d%H%M%S)"
  # Keep the 5 most recent rotated files
  find "$(dirname "$LOG_FILE")" -maxdepth 1 -type f \
       -name "$(basename "$LOG_FILE").*" -printf '%T@ %p\n' 2>/dev/null \
    | sort -rn | tail -n +6 | cut -d' ' -f2- | while read -r f; do rm -f "$f"; done
}

# ─── Main ────────────────────────────────────────────────────────────────
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
CPU=$(cpu_percent)
MEM=$(mem_percent)
LOAD=$(load_avg)
DISKS=$(disk_usage)
PROCS=$(top5_procs)

STATUS="healthy"
EXIT=0
WARNINGS=()

add_warning() {
  WARNINGS+=("$1")
  STATUS="warning"
  EXIT=1
}

[[ "$CPU" -ge "$CPU_THRESHOLD" ]] && add_warning "CPU ${CPU}% >= ${CPU_THRESHOLD}%"
[[ "$MEM" -ge "$MEM_THRESHOLD" ]] && add_warning "Memory ${MEM}% >= ${MEM_THRESHOLD}%"

while IFS=: read -r mount pct; do
  [[ -z "$mount" ]] && continue
  [[ "$pct" -ge "$DISK_THRESHOLD" ]] && add_warning "Disk ${mount} at ${pct}% >= ${DISK_THRESHOLD}%"
done <<< "$DISKS"

# ─── Emit ────────────────────────────────────────────────────────────────
json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }

if [[ "$JSON_OUTPUT" == "true" ]]; then
  DISKS_JSON="["
  first=true
  while IFS=: read -r m p; do
    [[ -z "$m" ]] && continue
    [[ "$first" == "true" ]] && first=false || DISKS_JSON+=","
    DISKS_JSON+="{\"mount\":\"$(json_escape "$m")\",\"used_percent\":$p}"
  done <<< "$DISKS"
  DISKS_JSON+="]"

  PROCS_JSON="["
  first=true
  while IFS=: read -r pid name rss; do
    [[ -z "$pid" ]] && continue
    [[ "$first" == "true" ]] && first=false || PROCS_JSON+=","
    PROCS_JSON+="{\"pid\":$pid,\"name\":\"$(json_escape "$name")\",\"rss_kb\":$rss}"
  done <<< "$PROCS"
  PROCS_JSON+="]"

  WARN_JSON="["
  first=true
  for w in "${WARNINGS[@]:-}"; do
    [[ -z "$w" ]] && continue
    [[ "$first" == "true" ]] && first=false || WARN_JSON+=","
    WARN_JSON+="\"$(json_escape "$w")\""
  done
  WARN_JSON+="]"

  OUTPUT=$(printf '{"timestamp":"%s","status":"%s","cpu_percent":%s,"memory_percent":%s,"load_average":"%s","disk":%s,"top_processes":%s,"warnings":%s}' \
    "$TS" "$STATUS" "$CPU" "$MEM" "$LOAD" "$DISKS_JSON" "$PROCS_JSON" "$WARN_JSON")
else
  OUTPUT="${TS} status=${STATUS} cpu=${CPU}% mem=${MEM}% load=${LOAD}"
fi

rotate_log
echo "$OUTPUT" >> "$LOG_FILE"

[[ "$QUIET" != "true" ]] && echo "$OUTPUT"

for w in "${WARNINGS[@]:-}"; do
  [[ -n "$w" ]] && echo "[WARNING] $w" >&2
done

exit "$EXIT"