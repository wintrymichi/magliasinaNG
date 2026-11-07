#!/usr/bin/env bash
# Switzerland Builder (macOS): double-click in Finder. The first start installs the app's own Python (5-10 minutes),
# then the app opens in the browser. Closing the Terminal window stops it.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/beamng/builder/launch/start.sh" "$@"
