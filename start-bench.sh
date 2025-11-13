#!/usr/bin/env bash
set -euo pipefail

# Always run from the bench root so relative paths resolve correctly
cd "$(dirname "$0")"

if [[ ! -x "./env/bin/bench" ]]; then
	echo "bench executable not found under ./env/bin" >&2
	exit 1
fi

# Ensure honcho from the virtualenv is on PATH before invoking bench start
export PATH="$PWD/env/bin:$PATH"
exec ./env/bin/bench start "$@"
