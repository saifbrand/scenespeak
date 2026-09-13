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

# The Android SDK: Gradle needs to be told where it is.
if [ -z "${ANDROID_HOME:-}" ] && [ ! -f app/local.properties ]; then
  for guess in "$HOME/Library/Android/sdk" "$HOME/Android/Sdk" "${LOCALAPPDATA:-}/Android/Sdk"; do
    if [ -d "$guess" ]; then export ANDROID_HOME="$guess"; break; fi
  done
fi
if [ -z "${ANDROID_HOME:-}" ] && [ ! -f app/local.properties ]; then
  echo "Set ANDROID_HOME to your Android SDK (Android Studio > Settings > Android SDK)." >&2
  exit 1
fi

# The film goes inside the APK. Without it the app installs and has nothing
# to play, which is worth stopping for rather than discovering on the TV.
if [ ! -f app/app/src/main/assets/film.mp4 ]; then
  echo "No film in the app yet -- fetching it (about 600 MB, once)." >&2
  tools/fetch_media.sh
fi

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
