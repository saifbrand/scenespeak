# Measurement

The claim is that **no description is ever spoken over dialogue.** This is how
it was checked, on *Tears of Steel* (12:14), including the run that went wrong.

Raw data is in [`measure/`](measure/): one tab-separated row per line the
Fire TV app spoke, written by the app itself on the device.

## 1. Where the film talks

Two independent sources, compared.

| | seconds | share of film |
|---|---:|---:|
| Subtitle cues, merged | 144.0 | 19.6% |
| Speech detected in the audio | 95.8 | 13.0% |
| **Union — what the planner uses** | **160.9** | **21.9%** |

Speech is detected by comparing the full mix with the film's music-and-effects
stem in the 300 Hz–3.4 kHz band (`describe/speechtrack.py`). The median extra
energy inside detected speech is **+10.8 dB**; outside it, 0.0 dB.

What the audio showed that the subtitles did not:

- speech runs past the end of its own subtitle cue in 15 places, by up to **1.07 s** (90th percentile 0.77 s)
- **13.8 s** of speech has no subtitle at all — including 4.2 s in the first ten seconds
- **62.0 s** of subtitle time has no speech under it (cues stay on screen after the line)

The consequence, measured: planning from subtitles alone produced 49 slots,
and **3 of them overlapped real speech**. Planning from the union produced 48,
and none did.

## 2. The track

Built by `python -m describe.cli --writer gemini`; every figure below is in
`out/tears_of_steel.json` under `stats`.

| | |
|---|---:|
| Description slots | 48 |
| Lines written | 35 |
| Slots where the writer judged nothing worth describing | 11 |
| Lines rewritten shorter because the first answer did not fit | 8 |
| Lines rewritten because they named a character too early | 1 |
| Lines dropped — would not fit even rewritten | 2 |
| Words | 578 |
| Estimated collisions with detected speech | 0 |

## 3. On the device

The app ran on an Android TV emulator at API 30 — the Android version behind
Fire OS 8 — with Google's text-to-speech engine, and played the whole film
three times.

### Run 1 — default timing constants

The speech-timing model's constants were guesses. The app logged how long each
line took to speak.

- 34 lines measured; none exceeded its slot by wall-clock duration
- the model was off by **0.50 s per line** on average
- fitting it to the measurements: the engine's fixed cost is **0.72 s**, not
  the 0.28 s guessed; per-syllable cost 0.188 s
- two lines were never spoken (see run 2)

Those fitted constants are `calibration.json`, and the track was rebuilt with them.

### Run 2 — the measurement was wrong, and so was the player

With the calibrated track, one line appeared to take **8.42 s in a 6.80 s
slot**, and **three lines were never spoken**.

Two separate problems, both found in this data:

1. **Wrong clock.** The app measured how long speech lasted in wall-clock
   time. The rule is about *film* time. On a software-rendered emulator the two
   drift: the film can advance six seconds while eight pass in the room. So
   this run could not say whether that line overran or not. The app now also
   records **where the film was when each line stopped**, which answers the
   question exactly (to within one 100 ms polling tick, which is added before
   judging, never subtracted).
2. **Start latency.** Lines started up to 0.25 s after their slot opened. The
   player — correctly — refuses to start a line that no longer fits what is
   left of its slot, so a line sized to the *whole* slot was silently skipped
   rather than cut off. The pipeline now sizes every line to the slot minus a
   0.3 s allowance (`START_LATENCY` in `describe/build.py`).

### Run 3 — the result

| | |
|---|---:|
| Lines in the track | 35 |
| **Lines spoken** | **35** |
| Lines that ended naturally (not cut off) | 35 |
| **Lines still speaking when their slot closed (film time)** | **0** |
| Smallest margin between a line ending and its slot closing | 0.58 s |
| Median margin | 3.61 s |
| **Lines overlapping speech detected in the audio (film time)** | **0** |
| Closest any description came to the next spoken word | **1.38 s** |
| Start lateness, median / worst | 0.09 s / 0.54 s |
| Total description spoken | 201.9 s |

The worst start was later than the 0.3 s allowance. It still finished 0.58 s
clear, because the slot's own guard margin (0.8 s before dialogue resumes) sits
behind the allowance; and had it not, the player's hard stop cuts the voice at
the end of the slot regardless of what any estimate said.

Refitting the timing model to run 3 gives an average error of 0.38 s per line.

## 4. On Amazon's own Fire TV devices

Amazon Appstore Automated Testing (Developer Console → Tools & Services →
Appstore Quality Central → Test Your App) installs an APK on real Fire TV
hardware, launches it, exits it and measures it. It was run twice on
13 September 2026, with the shrunk release build.

| Device | Fire OS | v1.0 | v1.1 |
|---|---|---|---|
| Fire TV Stick (Gen 2) | 5 | non-compatible | **compatible** |
| Fire TV Stick 4K | 6 | non-compatible | **compatible** |
| Fire TV Stick (3rd Gen) | 7 | compatible | **compatible** |
| Fire TV Stick 4K Max (2nd Gen) | 8 | compatible | **compatible** |
| **Overall** | | 2 of 4 | **4 of 4** |

v1.0 asked for Android 9 (Fire OS 7) without needing it, so the two older
sticks could not install it. v1.1 lowers that to Android 5.1 (Fire OS 5),
with fallbacks for the two newer APIs the app touches. Each run took about
30 minutes. The tests cover install, launch, exit and performance; they do
not check that descriptions avoid dialogue — that is sections 1–3.

## Reproducing it

```bash
tools/fetch_media.sh
python -m describe.cli --writer stub         # or --writer gemini with a key
tools/install_demo.sh                        # plays the film on the device
# after the film ends:
adb shell run-as com.saifbrand.scenespeak cat files/spoken.tsv > spoken.tsv
python tools/calibrate.py spoken.tsv out/tears_of_steel.json --out /dev/null
```

`calibrate.py` exits non-zero if any line was still speaking when its slot
closed.

## What this does not show

- The timing measurements in section 3 were made on an emulator. Amazon's
  automated testing (section 4) confirms the app installs, launches and
  runs on four real Fire TV sticks, but it does not repeat the film-time
  measurement there.
- Speech detection needs a music-and-effects stem. A film without one is
  planned from subtitles alone, which section 1 shows is weaker; the pipeline
  says so in its own output (`"sources": ["subtitles"]`).
- The speech detector is itself a measurement with an error. It is checked
  against the subtitles (it agrees where they agree), not against a
  hand-labelled transcript.
- Whether a description is *good* is not measured here. It was spot-checked
  against its frames by eye.
