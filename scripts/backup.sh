#!/usr/bin/env bash
# Dump the database to backups/scitracker-<UTC time>.dump (pg_dump custom format),
# check that the file is a readable archive, keep the newest BACKUP_KEEP files.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
dir=${BACKUP_DIR:-backups}
keep=${BACKUP_KEEP:-14}
mkdir -p "$dir"
file="$dir/scitracker-$(date -u +%Y%m%dT%H%M%SZ).dump"
trap 'rm -f "$file.part"' EXIT

docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$file.part"
[ -s "$file.part" ] || { echo "backup is empty" >&2; exit 1; }
docker compose exec -T db pg_restore --list < "$file.part" > /dev/null  # a damaged archive fails here
mv "$file.part" "$file"

# shellcheck disable=SC2012
ls -1t "$dir"/scitracker-*.dump | tail -n +"$((keep + 1))" | xargs -r rm --
echo "backup written: $file ($(du -h "$file" | cut -f1))"
