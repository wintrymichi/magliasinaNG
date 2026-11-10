#!/usr/bin/env bash
# switzerlandNG (Linux): updates the app to the newest version on GitHub (only the files that changed), then starts it.
# Builds, downloads and settings stay. --check only says whether one is out, --full downloads the whole version again.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/beamng/builder/launch/start.sh" update "$@"
