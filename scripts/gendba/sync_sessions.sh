#!/bin/bash
# sync_sessions.sh -- copy Claude session state to /proj, which is the only
# filesystem that survives the CloudLab allocation.
#
# Re-runnable: rsync only moves what changed, so run it as often as you like and
# again immediately before the machine goes away. The live transcript is appended to
# while a session is running, so any copy taken mid-session is already stale by the
# time it finishes -- that is expected, and the reason this is a script rather than a
# one-off command.
#
# Secrets are deliberately NOT copied: /proj is shared project storage. That means
# .credentials.json, and also sessions/ -- which holds per-session .key files -- plus
# any stray *.key/*.pem. plugins/ is excluded too: it is a re-downloadable marketplace
# cache, not session state, and it is most of the byte count and all of the noise in a
# "does this contain a credential" scan.
#
# What IS copied is the part that cannot be recreated: the conversation transcripts,
# the memory directory, history, file-history and settings.
set -u
SRC=${CLAUDE_HOME:-/users/$USER/.claude}
DST=${1:-/proj/pmoss-PG0/claude_sessions/latest}

mkdir -p "$DST"
rsync -a --delete \
  --exclude '.credentials.json' \
  --exclude '*.key' --exclude '*.pem' \
  --exclude 'ide/' --exclude 'cache/' --exclude 'paste-cache/' \
  --exclude 'plugins/' \
  "$SRC/" "$DST/"

echo "synced $(du -sh "$DST" | cut -f1) to $DST"
t="$DST/projects/-proj-pmoss-PG0-protox"
[ -d "$t" ] && {
  echo "  transcripts: $(ls -1 "$t"/*.jsonl 2>/dev/null | wc -l) "
  echo "  memory     : $(ls -1 "$t"/memory/*.md 2>/dev/null | wc -l) files"
  for f in "$t"/*.jsonl; do
    [ -e "$f" ] && echo "    $(basename "$f") $(wc -l < "$f") lines, $(wc -c < "$f") bytes"
  done
}
# Check for secret-bearing FILES, not the word. The transcripts discuss credentials
# as a topic, so a content grep matches its own safety check and cries wolf forever.
leak=$(find "$DST" \( -iname '*.key' -o -iname '*.pem' -o -iname 'id_rsa*' \
                     -o -iname '*credentials*' \) 2>/dev/null)
if [ -n "$leak" ]; then
  echo "  WARNING: secret-bearing files present on shared storage:"
  echo "$leak" | sed 's/^/    /'
else
  echo "  no key/credential files present"
fi
