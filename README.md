# SceneSpeak

**Audio description for Fire TV, generated for films that do not have it — and never spoken over the dialogue.**

A blind viewer watching a film gets the dialogue and nothing else. The fix
is audio description: a voice that says what is on screen, in the gaps where
nobody is speaking. It exists on a small fraction of titles, it is expensive
to produce, and in most languages it barely exists at all.

SceneSpeak generates one from the film itself and speaks it on Fire TV.
The whole project is built around a single rule that can be checked
rather than claimed:

> **A description may never be spoken over dialogue.**

Everything here — where descriptions go, how long they are allowed to be,
what happens when the voice runs long — follows from enforcing that rule and
then measuring whether it held.

**Try it without building anything:** download `SceneSpeak-1.0.apk` from
[the v1.0 release](https://github.com/saifbrand/scenespeak/releases/tag/v1.0)
and `adb install` it on a Fire TV or an Android TV emulator. The film is
inside.

## What it does

```
media/film.mp4 + subtitles + audio stems
        │
        ▼
  describe/   plan where the film is silent  →  write a line for each gap
        │                                        sized to the gap
        ▼
  out/tears_of_steel.json      the description track
        │
        ▼
  app/        Fire TV app: plays the film, speaks each line at its
              timestamp, ducks the film, hard-stops at the end of the gap
```

## The numbers, on *Tears of Steel*

Every figure below is computed by `python -m describe.cli`, not estimated.

| | |
|---|---|
| Film | 12:14 (734 s) |
| Dialogue | 161 s (**21.9%**) |
| Describable silence | 573 s (**78.1%**) |
| Description slots found | 48 |
| Lines written | 35 |
| Lines the writer declined to write (nothing worth describing) | 11 |
| Words spoken | 578 |
| **Collisions with measured speech** | **0** |
| Tightest estimated margin inside a slot | 0.48 s |

## The part that is not obvious

**Subtitles are not a safe map of when a film talks.** They are the obvious
input — every film has them — and used alone they are wrong often enough to
break the rule. Measured on this film, against its dialogue-free audio stem:

- real speech runs past the end of its own subtitle cue by up to **1.07 s**
- **13.8 s** of the film is spoken with no subtitle at all
- planning from the subtitle file alone put **3 of 49** descriptions on top
  of a voice

So the planner does not trust the subtitles. Where a film ships a
music-and-effects stem — as the Blender open movies do — `describe/speechtrack.py`
compares it with the full mix in the 300 Hz–3.4 kHz speech band and derives
where the film *actually* talks. The music is in both files, so it cancels
out of the comparison; what is left is a voice. On this film that difference
is **+10.8 dB** inside detected speech and **0.0 dB** outside it.

Subtracting the two waveforms does not work, incidentally — they are
separate renders, misaligned by 7 ms and mastered differently, so the
difference is mostly mastering. The comparison has to be made in the
frequency domain.

## Two more rules worth having

**Nobody is named before the film names them.** A description that says
"Vesper reaches for the syringe" before any character has said "Vesper" has
handed a blind listener a spoiler that a sighted viewer does not get. A
model writing from frames is prone to this because famous films' character
names are in its training data — and this one did it, at 6:51, with a name
that appears nowhere in the subtitles. `describe/names.py` learns the cast
from the film's own dialogue and sends any line that leaks a name back to be
rewritten.

**A line that will not fit is rewritten, not chopped.** Asking for a shorter
sentence returns a sentence. Cutting words off the end of a long one returns
"two wire-frame figures stand in a complex industrial".

## Running it

You need Python 3.10+ with `pip install -r requirements.txt`, and `ffmpeg`
on the PATH. For the app: JDK 17+ and the Android SDK, with `ANDROID_HOME`
set (Android Studio installs both).

```bash
tools/fetch_media.sh                     # the film, subtitles and stems (CC-BY)
python -m describe.cli --writer stub     # the whole pipeline, no key, no network
SCENESPEAK_GEMINI_KEY=... python -m describe.cli --writer gemini
python -m pytest tests/ -q               # 90 tests (plus 11 Kotlin tests in app/)
```

**Other languages.** `--language bn` (any BCP 47 tag) asks the writer for
that language, records it in the track, and the app picks its voice from
it. English is timed by syllable; other scripts are timed by written glyph
with vowel signs excluded, and need their own constants measured on the
device (`tools/calibrate.py --language bn`). Two honest limits: the spoiler
check relies on capital letters, so it cannot see names in scripts without
case, and whether a given Fire TV has a voice for the language is checked
by the app at startup, not assumed.

The vision writer is an interface with more than one implementation
(`describe/vision.py`), so the pipeline is not tied to one vendor's
endpoint; `--writer stub` exercises every other part of it with no model at
all.

## The Fire TV app

```bash
tools/install_demo.sh                    # build, install, launch
tools/install_demo.sh 192.168.1.42       # onto a Fire TV stick over the network
```

Kotlin, Jetpack Compose for TV, Media3/ExoPlayer, Android TextToSpeech.
`minSdk 28` covers Fire OS 7 and later; the demo runs on an Android TV
emulator at API 30, which is Fire OS 8.

The film goes inside the APK, so the installed app needs no sideloaded
media, no permission dialog and no configuration. The film itself is not in
this repository; `tools/install_demo.sh` fetches it on first run
(`tools/fetch_media.sh`, about 600 MB with the audio stems). A build made
without it opens on a screen that says so rather than a black one.

On the remote: **centre** toggles description, **play/pause** pauses both the
film and the voice, **left/right** skip thirty seconds.

## How the claim is checked on the device

The estimate of how long a line takes to speak is a model, and a model can
be wrong on a voice it has never heard. So the app writes down what every
line actually took:

```bash
adb shell run-as com.saifbrand.scenespeak cat files/spoken.tsv > spoken.tsv
python tools/calibrate.py spoken.tsv out/tears_of_steel.json
```

That fits the timing constants to the device's own voice and reports the
only number that matters: how many lines were still speaking, in film time,
when their silence ended. On the last full playback: **35 of 35 lines spoken,
0 overran, 0 overlapped real speech, nearest approach to a spoken word 1.38
s.** [MEASUREMENT.md](MEASUREMENT.md) has all three runs, including the one
that exposed a measurement error and a player bug.

## Licence and credits

Code: MIT. *Tears of Steel* © Blender Foundation, [CC BY 3.0](https://mango.blender.org)
— used as demo content and not redistributed from this repository;
`tools/fetch_media.sh` downloads it from Blender.

Built by **Shifullah** for the Build, Ship, Shape: Amazon Developer Hackathon.
