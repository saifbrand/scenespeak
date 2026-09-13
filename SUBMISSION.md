# Devpost submission — SceneSpeak (Fire TV track)

Draft answers. Numbers are filled from `out/tears_of_steel.json` and
`MEASUREMENT.md`; nothing here is claimed that the repo cannot reproduce.

---

## Project name

SceneSpeak

## Tagline

Audio description for Fire TV, generated for films that do not have it —
and never spoken over the dialogue.

## Elevator pitch / description

A blind viewer watching a film gets the dialogue and nothing else. Fights,
faces, a city on fire, somebody quietly leaving the room — none of it
reaches them. The fix has existed for decades: audio description, a voice
that says what is on screen in the gaps where nobody is speaking. It is on a
small fraction of titles, it costs real money to produce, and outside
English it barely exists at all.

SceneSpeak generates a description track from the film itself, and speaks it
on Fire TV.

It is built around one rule, chosen because it can be proved rather than
claimed: **a description may never be spoken over dialogue.** Everything
follows from that.

**How it works.**

1. The pipeline works out when the film is talking. Subtitles are the
   obvious source, and on their own they are not safe — see below.
2. The silences left over become description slots, pulled in at both ends
   by guard margins. The margins are deliberately asymmetric: starting a
   moment late just means saying less, while finishing late means talking
   over an actor.
3. For each slot it samples frames across the slot with ffmpeg and asks a
   vision model for one line *sized to that slot* — the request says how
   many seconds and roughly how many words are available.
4. The line is measured against a calibrated speech-timing model. A line
   that does not fit is sent back to be rewritten shorter, not chopped:
   asking for a shorter sentence returns a sentence, while cutting words off
   the end returns "two wire-frame figures stand in a complex industrial".
5. The Fire TV app plays the film, speaks each line at its timestamp, ducks
   the film to 22% while it speaks, and **hard-stops the voice at the end of
   the slot** whatever the estimate said.

**The part I did not expect.** Subtitles are not a safe map of when a film
talks. Tears of Steel ships a music-and-effects stem alongside its full mix,
so I could check. Measured against the real audio, speech runs past the end
of its own subtitle cue by up to **1.07 seconds**, and **13.8 seconds** of
the film is spoken with no subtitle at all. Planning from the subtitle file
alone put **3 of 49** descriptions on top of a voice.

So the planner does not trust subtitles. Where a film ships that stem, the
pipeline compares it with the full mix in the 300 Hz–3.4 kHz speech band and
derives where the film actually talks. Both files contain the same music, so
the music cancels out of the comparison and what is left is a voice: **+10.8
dB** inside detected speech, **0.0 dB** outside it. (Subtracting the
waveforms does not work — they are separate renders, 7 ms apart, mastered
differently. The comparison has to be in the frequency domain.)

**A second rule worth having.** The model called a character "Vesper" in a
line at 6:51. That name appears nowhere in the film's subtitles. A blind
listener would have been handed a character's name that no sighted viewer
gets — a spoiler delivered by the accessibility feature itself. So
`describe/names.py` learns the cast from the film's own dialogue and sends
any line that names somebody too early back to be rewritten.

**Tested by Amazon on real Fire TV hardware.** Amazon Appstore Automated
Testing installed, launched and measured the app on four Fire TV sticks —
Gen 2 (Fire OS 5), 4K (Fire OS 6), 3rd Gen (Fire OS 7) and 4K Max 2nd Gen
(Fire OS 8). **Compatible on all four.** (The first build passed only two:
it asked for a newer Android than it needed. Fixed in v1.1.)

**Results on Tears of Steel (12:14).** 78.1% of the film is describable
silence. 48 slots found, 35 lines written, 578 words, 11 slots where the
writer said there was nothing worth describing.

**Checked on the device, in film time.** The app records where the film was
when every line started and stopped. Playing the whole film on Fire OS 8:
all 35 lines spoken, **0 still speaking when their slot closed**, **0
overlapping speech detected in the audio**, and the closest any description
came to the next spoken word was **1.38 seconds**.

Getting there took three full playbacks, and the one that went wrong is the
most useful part of MEASUREMENT.md. The second run seemed to show a line
taking 8.4 s in a 6.8 s gap and three lines never spoken. The first was a
measurement error — wall-clock time on an emulator drifts from film time, so
the app now logs film position instead. The second was real: lines start up
to a quarter second late, and the player refuses to start a line that no
longer fits, so the pipeline now leaves room for that.

## Built with

Kotlin · Jetpack Compose for TV · AndroidX Media3 / ExoPlayer · Android
TextToSpeech · Python · numpy · ffmpeg · Gemini (vision) · Android TV
emulator at API 30 (Fire OS 8)

## Repository

https://github.com/saifbrand/scenespeak — MIT.

---

# Form answers

**Submitter Type:** Individual
**Organization Name:** N/A
**Country of Residence:** Bangladesh
**Canada province:** N/A
**Primary Track:** Fire TV
**Repository URL:** https://github.com/saifbrand/scenespeak
**New or existing:** New
**AWS Builder Mini Challenge:** No
**Which AWS services did you incorporate and how:** N/A — this project uses
no AWS services. The description pipeline runs locally against a vision
model, and the Fire TV app runs entirely on the device.
**Open Source Mini Challenge:** Yes
**Contribution URL:** https://github.com/saifbrand/scenespeak
**Project Repository URL:** https://github.com/saifbrand/scenespeak
**GitHub Username:** saifbrand
**Open Source description:** SceneSpeak is a new MIT-licensed project
created during the hackathon window. It is two things anybody can reuse: a
Python pipeline that turns a film plus its subtitles into a timed audio
description track that provably never overlaps dialogue, and a Kotlin Fire
TV app that speaks it. The parts that are useful on their own are the gap
planner, the speech-timing model that sizes a line to the silence it has,
the spoiler check that stops a description naming a character before the
film does, and the audio method that finds where a film really talks by
comparing its full mix with its music-and-effects stem in the speech band.
It matters because audio description exists on a small fraction of titles
and almost nothing outside English, and every piece here is open for someone
to point at another film, another language, or another player.
**Friction Log:** https://github.com/saifbrand/scenespeak/blob/main/FRICTION.md
**Project Testing Link:** https://github.com/saifbrand/scenespeak/releases/tag/v1.1 (ready-to-install APK, film included)

## Feedback 1 — which tools, APIs and SDKs did you use and for what?

- **Android SDK / Kotlin / Jetpack Compose + androidx.tv:tv-material** — the
  Fire TV app itself: one full-screen player, a description on/off state,
  and D-pad handling.
- **AndroidX Media3 (ExoPlayer)** — playing the film, reporting the playback
  position that drives every description, and volume ducking.
- **Android TextToSpeech** — speaking the description track, with
  `UtteranceProgressListener` used to measure how long each line really took.
- **Android TV emulator (API 30)** — the development device. I have no Fire
  TV hardware, so everything was built and measured against the Android
  version behind Fire OS 8.
- **adb** — install, launch, and `run-as` to read measurement files back off
  the device.
- **Python + numpy + ffmpeg** — the description pipeline: subtitle parsing,
  the speech-band audio analysis, frame sampling, and the timing model.
- **Amazon Appstore Automated Testing** — installing, launching and
  measuring the APK on real Fire TV sticks (Fire OS 5, 6, 7 and 8), since I
  have no hardware. It found that my first build excluded the two older
  sticks; the fixed build passed on all four.
- **Gemini (vision)** — writing the description for each gap from sampled
  frames. Behind an interface with a second implementation, so the pipeline
  is not tied to one vendor.

## Feedback 2 — what worked well?

The biggest thing: an ordinary Kotlin + Compose + Media3 app built with the
standard Android SDK runs on Fire OS unchanged. No Fire-specific SDK, no
device registration, no separate toolchain. For a developer on Windows with
no hardware, that is a genuinely low barrier and it is the reason this
project exists at all.

Amazon Appstore Automated Testing was the best surprise: free, no published
app needed, and within half an hour it had run my APK on four real Fire TV
sticks from Fire OS 5 to 8 and told me two of them could not install it.
Without it I would have shipped an app that silently excluded every Fire TV
Stick 4K first generation.

`androidx.tv:tv-material` sits alongside Compose without ceremony. D-pad
input through `onKeyDown` worked first time. Media3's player API is clean and its
position reporting is accurate enough to drive speech timing at ten ticks a
second.

## Feedback 3 — what needs work?

**Getting a media file onto an Android 11 / Fire OS 8 device is broken for
sideloaded apps, and sideloading is how you develop for Fire TV.** Three
routes, all dead:

1. Reading `/sdcard/Movies/...` as a file — blocked by scoped storage, as
   expected.
2. The app's own external directory, which is the documented answer:
   `adb shell mkdir` there returns *Permission denied*, `adb push` fails with
   *remote secure_mkdirs failed: Permission denied*, and one push reported
   success while writing nothing.
3. MediaStore with `READ_EXTERNAL_STORAGE` granted: `adb shell content query`
   finds the video, and the identical query from inside the app returns a
   valid cursor with **zero rows** — both after `pm grant` and after the user
   accepts the real permission dialog.

I ended up putting the film inside the APK. It makes the demo better, but it
is not something a real video app can do. Please either allow `adb push` into
a debuggable app's own external files directory, or document what a
sideloaded Fire TV app is supposed to do about media under Fire OS 8.

**`TextToSpeech.SUCCESS` does not mean it can speak.** Google's engine
returned SUCCESS from its init callback and then failed the first real
utterance with `synthesizeWithoutLoadingVoice()`; the voice finished loading
**eight seconds later**. For an accessibility app on a television, the first
thing it says is the thing that tells a blind user it is working. I now
speak an 80 ms silent utterance at startup to force the load.

**`UtteranceProgressListener` callbacks arrive on a binder thread and this
is not documented.** Touching the player from `onDone` throws inside the
binder transaction, where the system logs a warning and swallows it — the
app keeps running and everything after that line in the callback silently
never happens. It cost a full twelve-minute measurement run that produced an
empty file with no error. One sentence in the class documentation would have
prevented it.

**Vega OS ruled itself out late.** It is presented first, and the line that
matters — macOS/Linux only, and no sideloading on Vega devices — is not
where the decision gets made. A one-line platform matrix on the "choose your
path" page would save a Windows developer an hour.

**Automated testing gives no reasons.** My 87.5 MB APK upload stopped at 42%
with only "Upload failed" — no size limit shown, no error. And the summary
marked two sticks non-compatible without saying why; the cause was my
minimum Android version, which the upload step could have flagged in a
second instead of after a 30-minute run.

**Smaller:** `sdk.dir` in `local.properties` silently mangles a Windows path
written with single backslashes and fails with `java.io.IOException: Invalid
file path`, naming neither the file nor the property. And an app without
`LEANBACK_LAUNCHER` plus `android:banner` installs, reports success, and
then cannot be opened with a remote.

Full log with steps, expected vs. actual, severity and suggestions:
https://github.com/saifbrand/scenespeak/blob/main/FRICTION.md

## Feedback 4 — how was onboarding?

Fire OS was the easiest part. From "I have no Fire TV device and I am on
Windows" to an APK running on screen was about two hours, almost all of it
ordinary Android work I already knew. Nothing had to be requested, approved
or registered.

The Android TV emulator is the weak point of onboarding, and not because of
Amazon: there is no Fire TV image, so you build an Android TV AVD and take
it on faith that Fire OS behaves the same. It mostly does, but you cannot
check the differences you were warned about, which is an uncomfortable place
to develop from. I found out late that Amazon hosts real Fire TV devices for remote
testing (Live Device Interaction) — that deserves to be much louder in the
Fire TV getting-started path than it is.

## Feedback 5 — would you build with these again?

Yes, for Fire TV. The platform asks for almost nothing beyond ordinary
Android skills, the television form factor makes you design better because
the remote gives you five buttons and no excuses, and accessibility on a
television is a place where a small app can matter to somebody's evening.

No for Vega, until the tools run on Windows — not a judgement on the
platform, just that I cannot build for it.

The one change that would most improve the experience is the storage one
above. I spent more time trying to get a video file onto the device than I
spent writing the player.

## Feature requests

1. **`adb push` into a debuggable app's own external files directory.**
   *Why:* today there is no working way to get a large media file onto a
   Fire TV for development. `run-as` already reaches internal storage, so
   there is no new security ground being broken. *Priority: Critical.*
2. **A Fire OS system image for the Android emulator.** *Why:* everyone
   developing without hardware is testing on an approximation and hoping.
   *Priority: Important.*
3. **A documented "voice ready" signal for TextToSpeech**, or make
   `SUCCESS` mean ready. *Why:* every accessibility app on Fire TV loses its
   first utterance today. *Priority: Important.*
4. **Thread-safety documentation for `UtteranceProgressListener`.**
   *Why:* one sentence, and the failure it prevents is invisible.
   *Priority: Nice-to-have, but free.*
