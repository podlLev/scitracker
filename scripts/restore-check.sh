#!/usr/bin/env bash
# Restore a dump into a throw-away database and compare key tables with the live one.
# Usage: scripts/restore-check.sh backups/scitracker-<time>.dump
set -euo pipefail
cd "$(dirname "$0")/.."
file=${1:?usage: restore-check.sh <dump file>}
[ -f "$file" ] || { echo "no such file: $file" >&2; exit 1; }
tmp="restore_check_$(date +%s)"

psql_in() {  # psql_in <database> <sql>: run inside the db container, print the bare value
  docker compose exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d $1 -At -c \"$2\""
}
cleanup() {
  docker compose exec -T db sh -c "dropdb -U \"\$POSTGRES_USER\" --if-exists $tmp" > /dev/null
}
trap cleanup EXIT

docker compose exec -T db sh -c "createdb -U \"\$POSTGRES_USER\" $tmp"
docker compose exec -T db sh -c "pg_restore -U \"\$POSTGRES_USER\" -d $tmp --no-owner --exit-on-error" < "$file"

printf '%-18s %10s %10s\n' table live restored
status=0
for table in publications authors users topics reading_items status_changes notes; do
  live=$(psql_in '$POSTGRES_DB' "select count(*) from $table")
  restored=$(psql_in "$tmp" "select count(*) from $table")
  printf '%-18s %10s %10s\n' "$table" "$live" "$restored"
  [ "$restored" -le "$live" ] || status=1  # a restore can never have MORE rows than the source
done
version=$(psql_in "$tmp" "select version_num from alembic_version")
[ -n "$version" ] || { echo "alembic_version is empty" >&2; status=1; }
echo "schema version: $version"
[ "$status" -eq 0 ] && echo "restore check passed" || echo "restore check FAILED" >&2
exit "$status"
