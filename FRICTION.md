# Friction log — building SceneSpeak for Fire TV

Written while building, not reconstructed afterwards. Each entry follows the
hackathon's format: the task, the steps taken, what was expected against what
actually happened, a severity, the workaround, and a suggestion.

**Environment:** Windows 11 · no Fire TV hardware · Android Studio's JDK 21 ·
Android SDK platform 34 · Gradle 8.12 · AGP 8.7.3 · Kotlin 2.0.21 · Android TV
emulator at API 30 (the Android version behind Fire OS 8) ·
`com.google.android.tts`.

**Severity scale:** *Blocker* — no way forward without a workaround ·
*High* — hours lost or a wrong result produced silently · *Medium* — under an
hour · *Low* — minutes.

| # | Area | Severity | Time lost |
|---|---|---|---|
| 1 | Getting a media file onto a Fire OS 8 app | **Blocker** | ~2 h |
| 2 | TTS callbacks swallow exceptions on a binder thread | **High** | ~1 h + a 12-min run |
| 3 | `TextToSpeech.SUCCESS` before the voice can speak | **High** | ~30 min |
| 4 | Choosing Vega vs Fire OS on Windows | Medium | ~1 h |
| 5 | Reading data back off the device | Medium | ~20 min + a 12-min run |
| 6 | Recording the emulator with its sound | Medium | ~45 min |
| 7 | `local.properties` on Windows | Low | ~20 min |
| 8 | Leanback launcher and banner | Low | ~10 min |

---

## 1. Getting a media file onto a Fire OS 8 app

**Task.** Put a 55 MB film on the device so a sideloaded development build can play it.

**Steps.**
1. Pushed to `/sdcard/Movies/scenespeak/film.mp4`; opened it as a `File`.
2. Pushed into the app's own directory, `getExternalFilesDir()` → `/sdcard/Android/data/<pkg>/files/`.
3. Pushed to the public Movies folder, triggered a media scan, granted `READ_EXTERNAL_STORAGE` (first with `pm grant`, then through the real permission dialog), and queried MediaStore.

**Expected.** At least the documented route (2) or the MediaStore route (3) works for a debuggable app.

**Actual.**
1. Blocked by scoped storage — expected on Android 11.
2. `adb shell mkdir` there: *Permission denied*. `adb push`: *remote secure_mkdirs failed: Permission denied*. One push reported **success** and the file was not there afterwards.
3. `adb shell content query --uri content://media/external/video/media` returns the film. The identical query from inside the app returns **a valid cursor with zero rows** — after `pm grant` and after accepting the dialog.

**Workaround.** Shipped the film inside the APK and played `asset:///film.mp4`. It makes the demo one command, but it is not a route a real video app can take.

**Suggestion.** Allow `adb push` into a *debuggable* app's own external files directory (`run-as` already reaches its internal storage, so no new ground is broken), and document what a sideloaded Fire TV app is meant to do about media under Fire OS 8. Nothing in the Fire TV docs covers it today.

---

## 2. TTS callbacks swallow exceptions on a binder thread

**Task.** When a spoken line finishes, restore the film's volume and write a measurement row.

**Steps.** Called `exoPlayer.volume = 1f` and wrote the file from `UtteranceProgressListener.onDone`. Played the whole film.

**Expected.** Either it works, or it crashes loudly.

**Actual.** `onDone` runs on a binder thread. Touching ExoPlayer there throws — inside the binder transaction, where the system logs a `Binder` warning and swallows it. The app kept running, the film kept playing, the voice kept speaking, and everything after that line of the callback silently never happened. A full twelve-minute run produced an empty measurement file and no error anywhere visible.

**Workaround.** Write the file first, then post all player and UI work to `Handler(Looper.getMainLooper())`.

**Suggestion.** One sentence in the `UtteranceProgressListener` reference: *callbacks arrive on a binder thread; post to your own thread before touching UI or player state.* The class documentation says nothing about threading.

---

## 3. `TextToSpeech.SUCCESS` before the voice can speak

**Task.** Speak the film's first description ten seconds in.

**Steps.** Created `TextToSpeech`, waited for the init callback to report `SUCCESS`, then called `speak()` when the line was due.

**Expected.** `SUCCESS` means the engine can speak.

**Actual.** `speak()` returned `SUCCESS`; the engine then logged `synthesizeWithoutLoadingVoice() failed` and `callback.start() returned error code: -1`, and the listener got `onError` with no reason. Init succeeded at 17:45:15; the voice finished loading at **17:45:23**. The first description of the film was lost.

**Workaround.** `playSilentUtterance(80, QUEUE_FLUSH, "warm-up")` straight after init, which forces the voice to load while the opening logos are on screen.

**Suggestion.** Make `SUCCESS` mean ready to speak, or add a documented "voice loaded" signal. For an accessibility app on a television, the first thing it says is how a blind user learns it works.

---

## 4. Choosing Vega vs Fire OS on Windows

**Task.** Pick a Fire TV platform to build on from a Windows machine.

**Steps.** Started with Vega OS, which the hackathon resources list first; read its getting-started material and toolchain pages.

**Expected.** Platform requirements up front.

**Actual.** The deciding line — Vega tooling is "Mac or Linux machines only. Windows and WSL are not currently supported" — sits in the toolchain setup, after the introduction. Vega devices also do not allow sideloading at all.

**Workaround.** Fire OS with an ordinary Kotlin app, which needs nothing Windows cannot do.

**Suggestion.** A one-line matrix at the top of the "choose your path" page: *Vega — macOS/Linux, no sideloading · Fire OS — any OS, sideload over ADB.*

---

## 5. Reading data back off the device

**Task.** Get the app's measurement file off the device after a run.

**Steps.** Wrote it to `getExternalFilesDir()`; ran `adb pull`.

**Expected.** The app's own external directory is readable over adb on a debuggable build.

**Actual.** `adb pull`: *failed to stat remote object: Permission denied.*

**Workaround.** Write to `filesDir` and read with `adb shell run-as <pkg> cat files/spoken.tsv`.

**Suggestion.** Say this in the Fire TV developer tools docs. On a television there is no Files app and no share sheet; `run-as` plus internal storage is the only reliable way to get data off, and it is not where anyone looks first.

---

## 6. Recording the emulator with its sound

**Task.** Record the app running, with the film and the spoken descriptions audible, for the demo video.

**Steps.**
1. scrcpy 4.1 (`--audio-source=output`): first failed with *Could not create default audio encoder for opus*; with `--audio-codec=aac` it recorded, but the audio peaked at −40 dB — a faint residue.
2. `adb emu screenrecord start <file>` on a `-gpu swiftshader_indirect` emulator.
3. The same on a `-gpu host` emulator.

**Expected.** A recording that plays the film at true speed with clean audio.

**Actual.**
1. No usable audio from the device side on this image.
2. Real audio, but the recorder's software VP9 encode starved playback: the film ran at **0.88×** and the audio had **~42 dropouts** of 40–180 ms in two minutes. With a path containing spaces, the console answered *KO: Must specify output file*.
3. True-speed playback, 3 dropouts in 40 s.

**Workaround.** Boot the emulator with `-gpu host`, record with `adb emu screenrecord` to a path without spaces, and raise the emulator's media volume first (it defaults to 3 of 15).

**Suggestion.** For Fire TV specifically: a documented way to capture a demo with audio. The hackathon requires a video of the app running, and an accessibility app is mostly audio.

---

## 7. `local.properties` on Windows

**Task.** Point Gradle at the Android SDK.

**Steps.** Wrote `sdk.dir=C:\Users\...\Android\Sdk`.

**Expected.** The build finds the SDK.

**Actual.** `java.io.IOException: Invalid file path` — naming neither the file nor the property. It is a Java properties file, so single backslashes were silently eaten.

**Workaround.** Forward slashes: `sdk.dir=C:/Users/.../Android/Sdk`.

**Suggestion.** For AGP: name the file and property in the error, or accept native Windows paths.

---

## 8. Leanback launcher and banner

**Task.** Make the installed app launchable from the Fire TV home screen.

**Expected / actual.** An app without `android.intent.category.LEANBACK_LAUNCHER` and `android:banner` installs and reports success, then cannot be opened with a remote. Documented, but in a place you find after it has happened.

**Workaround.** Both declared from the start.

**Suggestion.** Have `adb install` or the build warn when a package targeting TV lacks either.

---

## What went well

- An ordinary Kotlin + Compose + Media3 app, built with the standard Android SDK, runs on Fire OS unchanged — no Fire-specific SDK, no registration, no device. That low barrier is why this project exists.
- `androidx.tv:tv-material` sits alongside Compose without ceremony; D-pad input through `onKeyDown` worked first time.
- Media3's playback position is accurate enough to drive speech timing at ten ticks a second.
- Nothing here is emulator-specific: Fire TV's documented ADB-over-network setup uses the same install and launch commands. (Not yet tried on a physical stick — see MEASUREMENT.md.)

The platform was not the hard part. Getting a file onto it — and a recording off it — was.
