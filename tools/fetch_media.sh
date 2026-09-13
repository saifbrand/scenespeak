#!/usr/bin/env bash
# Fetch the demo film. Nothing in media/ is committed: it is 600 MB of
# somebody else's film, and it is all a public download away.
#
# Tears of Steel (c) Blender Foundation, CC BY 3.0, mango.blender.org
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p media

base="https://download.blender.org/demo/movies/ToS"
get() { [ -f "media/$2" ] || curl -fL --progress-bar -o "media/$2" "$base/$1"; }

get "subtitles/TOS-en.srt"            TOS-en.srt
get "tears_of_steel_720p.mov"         tears_of_steel_720p.mov

# The two audio stems. These are what let the pipeline find the film's real
# speech instead of trusting the subtitle timings, which is the whole point
# of speechtrack.py. Without them the pipeline still runs; it just plans
# from subtitles alone and says so in its own output.
get "TOS_DVDSTEREOMIX.aif"            full_mix.aif
get "TOS_MUSIC%2BFX_NO_DIALOGUE.aif"  no_dialogue.aif

# A lighter copy for the Fire TV app and its emulator.
if [ ! -f media/film.mp4 ]; then
  ffmpeg -v error -y -i media/tears_of_steel_720p.mov -vf "scale=854:-2" \
    -c:v libx264 -profile:v main -preset veryfast -crf 26 \
    -c:a aac -b:a 128k -movflags +faststart media/film.mp4
fi

# The Fire TV app carries the film inside the APK so it plays with no setup.
# The asset is not committed, so it is copied in here.
mkdir -p app/app/src/main/assets
cp media/film.mp4 app/app/src/main/assets/film.mp4

ls -lh media/ app/app/src/main/assets/
