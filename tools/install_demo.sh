#!/usr/bin/env bash
# Build the app, put it on whatever is plugged in, and start it.
#
#   tools/install_demo.sh            # a running emulator or Fire TV over adb
#   tools/install_demo.sh 192.168.1.42   # a Fire TV stick on the network
set -euo pipefail
cd "$(dirname "$0")/.."

if [ $# -ge 1 ]; then
  adb connect "$1:5555"
fi

# The film is inside the APK, so there is nothing to push and no permission
# to grant. This is one command and then it is running.
( cd app && ./gradlew --console=plain assembleDebug )
adb install -r app/app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.saifbrand.scenespeak/.MainActivity

cat <<'KEYS'

Playing. On the remote:
  centre / OK      description on and off
  play-pause       pause the film (the voice stops with it)
  left / right     skip thirty seconds

To read back what the voice actually did:
  adb shell run-as com.saifbrand.scenespeak cat files/spoken.tsv > spoken.tsv
  python tools/calibrate.py spoken.tsv out/tears_of_steel.json
KEYS
