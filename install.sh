#!/bin/sh
# One-line installer for agent_talk (macOS, Linux, Git Bash on Windows):
#
#   curl -fsSL https://raw.githubusercontent.com/Misaka16384/agent-talk/main/install.sh | sh
#
# Arguments after `sh -s --` go to install.py, e.g. to uninstall:
#
#   curl -fsSL https://raw.githubusercontent.com/Misaka16384/agent-talk/main/install.sh | sh -s -- --uninstall
#
# It downloads the repository into a temporary folder, runs install.py, and deletes the folder.
set -eu

REPO="${AGENT_TALK_REPO:-Misaka16384/agent-talk}"
REF="${AGENT_TALK_REF:-main}"

PY=""
for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 &&
        "$c" -c 'import sys; sys.exit(sys.version_info < (3, 7))' >/dev/null 2>&1; then
        PY="$c"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "agent_talk: Python 3.7 or newer is required." >&2
    exit 1
fi

TMP=$(mktemp -d 2>/dev/null || mktemp -d -t agent_talk)
trap 'rm -rf "$TMP"' EXIT INT TERM

URL="https://codeload.github.com/$REPO/tar.gz/$REF"
if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$URL" | tar -xzf - -C "$TMP"
elif command -v wget >/dev/null 2>&1; then
    wget -qO- "$URL" | tar -xzf - -C "$TMP"
else
    echo "agent_talk: curl or wget is required." >&2
    exit 1
fi

SRC=$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n 1)
"$PY" "$SRC/install.py" "$@"
