#!/usr/bin/env bash
# Switzerland Builder (Linux): start it from a terminal or by double-click (Run). The first start installs the app's own
# Python (5-10 minutes), then the app opens in the browser. Ctrl+C or closing the terminal stops it.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/beamng/builder/launch/start.sh" "$@"
