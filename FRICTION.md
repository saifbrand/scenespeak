# Friction log — building SceneSpeak for Fire TV

Written while building, not reconstructed afterwards. Every item cost real
time on a real build; each one says what happened, what it cost, and what
would have prevented it.

Environment: Windows 11, no Fire TV hardware, Android Studio's JDK 21,
Android SDK build-tools 34/36/37, Gradle 8.12, AGP 8.7.3, Kotlin 2.0.21,
Android TV emulator at API 30 (the Android version behind Fire OS 8).

---

## 1. Vega OS is unbuildable on Windows, and the docs say so late

**What happened.** Vega is presented first in the hackathon's own resources,
so it is where a new developer starts. The toolchain requirements — "Mac or
Linux machines only. Windows and WSL are not currently supported" — are not
where the decision gets made. Worse, Vega devices do not allow sideloading
at all, so there is no route from a Windows machine to a running app even
with a device in hand.

**Cost.** About an hour, spent reading Vega documentation before finding the
line that ruled it out.

**What would have helped.** A one-line platform matrix at the top of the
"choose your path" page: *Vega — macOS/Linux only, no sideloading. Fire OS —
any OS, sideload over ADB.* A developer on Windows could then pick Fire OS
in ten seconds instead of an hour.

---

## 2. Android 11 scoped storage has no working path for sideloaded media

This was the single biggest time cost of the build, and it is a Fire TV
problem specifically, because sideloading *is* how you get content onto a
Fire TV stick for development.

**What happened.** Three approaches, in order:

1. `File("/sdcard/Movies/scenespeak/film.mp4")` — blocked. Expected on
   Android 11; fine.
2. The app's own external directory, `getExternalFilesDir()`. This is the
   documented answer, and it does not work from the outside:
   `adb shell mkdir` on that path is `Permission denied`, and `adb push`
   fails with `remote secure_mkdirs failed: Permission denied`. Confusingly,
   one push *reported success* and the file was not there afterwards.
3. MediaStore, with `READ_EXTERNAL_STORAGE` granted. `adb shell content
   query --uri content://media/external/video/media` returns the film. The
   same query from inside the app returns **a valid cursor with zero rows**,
   both after `pm grant` and after accepting the real permission dialog.

**Cost.** Roughly two hours, and a rebuild of the media layer twice.

**What would have helped.** Either of:
- `adb push` into an app's own external files directory on a debuggable
  build. The app is marked debuggable; `run-as` already reaches internal
  storage. There is no security argument for blocking the one directory the
  app owns.
- A documented statement of what a sideloaded Fire TV app is *supposed* to
  do about media files under Fire OS 8. Every path above is either blocked
  or silently empty, and no Fire TV documentation addresses it.

**What I did instead.** Put the film inside the APK. It makes the demo
better — install and it plays, no setup — but it is not a route a real video
app could take, and I only arrived at it after everything else failed.

---

## 3. `run-as` reaches internal storage, so that is where evidence has to live

**What happened.** The app writes a measurement file recording how long each
spoken line actually took. Written to `getExternalFilesDir()` it could not
be read back: `adb pull` gives `failed to stat remote object: Permission
denied`. Moving it to `filesDir` and reading it with `adb shell run-as
<pkg> cat files/spoken.tsv` works.

**Cost.** Twenty minutes, plus one wasted twelve-minute playback run.

**What would have helped.** This is worth a line in the Fire TV
developer-tools documentation, because on a television there is no Files app
to fall back on and no way to email yourself a log. `run-as` + internal
storage is the only reliable way to get data off a Fire TV, and it is not
where anybody looks first.

---

## 4. Text-to-speech has an eight-second cold start, and the first line is lost

**What happened.** `com.google.android.tts` reports `TextToSpeech.SUCCESS`
from its init callback while its voice is still being fetched and
initialised. Speaking immediately after that produced
`TTS.LocalSynthesizer: synthesizeWithoutLoadingVoice() failed` and
`callback.start() returned error code: -1`. Timestamps: init succeeded at
17:45:15, the voice finished initialising at **17:45:23**. The first
description of the film was thrown away.

**Cost.** Half an hour to diagnose, because the failure is silent from the
app's point of view — `speak()` returns `SUCCESS` and `onError` arrives with
no reason.

**What would have helped.** `TextToSpeech.SUCCESS` should mean ready to
speak, or there should be a documented "voice loaded" signal. For an
accessibility app on a television this matters more than on a phone: the
first thing the app says is the thing that tells a blind user it is working.

**Workaround, now in the code.** `playSilentUtterance(80, QUEUE_FLUSH,
"warm-up")` at startup, which forces the voice to load while the studio
logos are still on screen.

---

## 5. TTS callbacks arrive on a binder thread, and the exception is swallowed

**What happened.** `UtteranceProgressListener.onDone` is called on a binder
thread. The listener restored the player's volume after ducking —
`exoPlayer.volume = 1f` — which throws, because ExoPlayer must be touched
from the thread that created it. The exception is raised *inside a binder
transaction*: the system logs a `Binder` warning and swallows it. The app
keeps running, the film keeps playing, the voice keeps speaking, and the
only symptom is that everything after that line in the callback silently
never happens. In my case that was the measurement file — so a full
twelve-minute run produced an empty file and no error anywhere.

**Cost.** One wasted twelve-minute run and about forty minutes of hunting,
including one dead end investigating file permissions that were fine.

**What would have helped.** One sentence in the `UtteranceProgressListener`
documentation: *these callbacks arrive on a binder thread; post to your own
thread before touching UI or player state.* The class documentation says
nothing about threading at all.

---

## 6. Smaller things that still cost time

- **`sdk.dir` in `local.properties` is a Java properties file**, so a
  Windows path written with single backslashes is silently mangled and the
  build fails with `java.io.IOException: Invalid file path` — which names
  neither the file nor the property. Forward slashes work. *(20 minutes.)*
- **No `java` on `PATH`** after an Android Studio install; `sdkmanager`
  responds by printing nothing at all and exiting zero, rather than saying
  `JAVA_HOME` is unset. *(Known from earlier work; would have cost an hour.)*
- **`LEANBACK_LAUNCHER` and `android:banner` are mandatory** for an app to
  appear on the Fire TV home screen. An app without them installs, reports
  success, and then cannot be launched with a remote. This is documented,
  but it is documented in a place you only find after it has happened.
- **The Android TV emulator needs ~2.5 GB free RAM** and `-gpu
  swiftshader_indirect` to boot reliably on a machine also running a build.

---

## What went well, and is worth saying

- An ordinary Kotlin + Compose + Media3 app built with the standard Android
  SDK runs on Android TV/Fire OS unchanged. No Fire-specific SDK, no
  registration, no device. That is a genuinely low barrier.
- `androidx.tv:tv-material` and Compose work together without ceremony.
- D-pad handling through `onKeyDown` is the same as it has been for a
  decade, and works the first time.
- `adb connect <ip>:5555` to a real stick is the same flow as the emulator,
  so everything built against the emulator transfers.

The platform was not the hard part. Getting a file onto it was.
