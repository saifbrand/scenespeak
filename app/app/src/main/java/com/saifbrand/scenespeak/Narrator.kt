package com.saifbrand.scenespeak

import android.content.Context
import android.media.AudioAttributes
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import java.io.File
import java.util.Locale

/**
 * Speaks the description track, and stops speaking on time.
 *
 * The pipeline decides *what* is said and estimates how long it will take.
 * This class is what makes the guarantee true on a real device, where the
 * estimate can be wrong: a voice the pipeline never measured, a viewer who
 * has turned the speech rate down, an engine that starts late. So the
 * budget is enforced here, at playback, rather than trusted from the file.
 *
 * Three things have to happen for a description to be usable:
 *  - it starts when its slot starts, not when the previous one finishes;
 *  - it is cut off at the end of its slot, even mid-word, because the
 *    alternative is talking over the actor;
 *  - the film gets quieter while it speaks, because a description
 *    competing with an explosion is not a description.
 */
class Narrator(
    context: Context,
    private val onSpeaking: (Description?) -> Unit,
    private val onDuck: (Float) -> Unit,
) {
    /** How loud the film is left while a description is being spoken. */
    private val duckedVolume = 0.22f

    /** The thread the player and the screen belong to. */
    private val main = Handler(Looper.getMainLooper())

    private var engine: TextToSpeech? = null
    private var ready = false

    /** The line currently being spoken, and when its time is up. */
    private var speaking: Description? = null
    private var deadlineMs: Long = 0

    /** Lines already spoken, so a paused film does not repeat one. */
    private val done = HashSet<Long>()

    /** What actually happened, for the measurement that backs the claim. */
    private val log = StringBuilder()
    private var startedAtWall = 0L
    private var startedAtPosition = 0L

    /**
     * Where the film was on the last tick, readable from the binder thread.
     *
     * The rule is about the film's clock, not the room's. On a loaded
     * emulator the two drift apart -- a line can take 8.4 seconds of wall
     * time while the film advances only 6 -- so "how long did it speak"
     * cannot decide whether it overlapped anything. "Where was the film when
     * it stopped" can. At most one tick stale, which is 100 ms.
     */
    @Volatile private var lastPositionMs = 0L

    /**
     * The voice's language, taken from the track.
     *
     * A Bengali track read by an English voice is not a degraded experience,
     * it is gibberish, so a language the engine has no voice for is logged
     * loudly rather than quietly spoken in the wrong one.
     */
    var language: String = "en"
        set(value) {
            field = value
            if (ready) applyLanguage()
        }

    private fun applyLanguage() {
        val result = engine?.setLanguage(Locale.forLanguageTag(language))
        if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
            Log.e(TAG, "This device has no voice for '$language' (result $result)")
        }
    }

    var enabled: Boolean = true
        set(value) {
            field = value
            if (!value) silence()
        }

    init {
        engine = TextToSpeech(context) { status ->
            if (status != TextToSpeech.SUCCESS) {
                Log.w(TAG, "No text-to-speech engine is available on this device")
                return@TextToSpeech
            }
            applyLanguage()
            engine?.apply {
                setAudioAttributes(
                    AudioAttributes.Builder()
                        // Telling the platform this is accessibility speech
                        // is what lets it survive a viewer muting the film,
                        // and what marks it as speech to anything listening.
                        // The accessibility usage exists from Android 8; the
                        // Fire OS 5 and 6 sticks are older, and there the
                        // voice is ordinary media audio instead.
                        .setUsage(
                            if (android.os.Build.VERSION.SDK_INT >= 26)
                                AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY
                            else AudioAttributes.USAGE_MEDIA
                        )
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) {
                        startedAtWall = System.currentTimeMillis()
                    }

                    override fun onDone(utteranceId: String?) {
                        record(utteranceId, "done")
                    }

                    @Deprecated("Required by the base class")
                    override fun onError(utteranceId: String?) {
                        record(utteranceId, "error")
                    }

                    override fun onStop(utteranceId: String?, interrupted: Boolean) {
                        record(utteranceId, if (interrupted) "cut-off" else "stopped")
                    }
                })
            }
            // Speak nothing, immediately. Google's engine does not load a
            // voice until it is first asked to say something, and on a cold
            // Fire TV that download and initialisation took eight seconds --
            // long enough that the first real description of the film was
            // thrown away with "synthesizeWithoutLoadingVoice() failed".
            // A silent utterance at startup pays that cost while the studio
            // logos are still on screen.
            engine?.playSilentUtterance(80, TextToSpeech.QUEUE_FLUSH, "warm-up")
            ready = true
        }
    }

    /**
     * Called on every tick of playback.
     *
     * [positionMs] is the film's own clock, not the wall clock, which is
     * what makes pausing, seeking and buffering behave: a description
     * belongs to a moment in the film, so it is driven by where the film
     * is, never by how much time has passed in the room.
     */
    fun update(track: DescriptionTrack, positionMs: Long, playing: Boolean) {
        lastPositionMs = positionMs
        if (!ready) return

        if (!playing) {
            // Pausing the film stops the voice. Continuing to talk over a
            // frozen frame is disorienting, and the line will be spoken
            // again from its own start when playback resumes.
            if (speaking != null) {
                speaking?.let { done.remove(it.startMs) }
                silence()
            }
            return
        }

        speaking?.let { current ->
            // The hard stop. Whatever the estimate said, the slot is over.
            if (positionMs >= current.endMs || positionMs < current.startMs) {
                silence()
            }
        }

        if (!enabled) return

        val due = track.at(positionMs) ?: return
        if (due.startMs == speaking?.startMs) return
        if (done.contains(due.startMs)) return

        // Starting late in a slot leaves less room than the line was
        // written for, so it is skipped rather than started and cut. That
        // happens after a seek, which is exactly when a half-spoken
        // sentence would be most confusing.
        val remaining = due.endMs - positionMs
        if (remaining < due.estimatedMs && remaining < due.budgetMs) {
            done.add(due.startMs)
            return
        }

        speak(due, positionMs)
    }

    private fun speak(line: Description, positionMs: Long) {
        speaking = line
        deadlineMs = line.endMs
        done.add(line.startMs)
        startedAtPosition = positionMs
        onDuck(duckedVolume)
        onSpeaking(line)
        engine?.speak(line.text, TextToSpeech.QUEUE_FLUSH, null, line.startMs.toString())
    }

    /** Stop the voice at once and give the film its volume back. */
    private fun silence() {
        if (speaking != null) {
            engine?.stop()
            speaking = null
            onSpeaking(null)
            onDuck(1f)
        }
    }

    /** A seek means the film is somewhere else; nothing spoken still applies. */
    fun seeked() {
        done.clear()
        silence()
    }

    /** Set once, so measurements can be flushed as they happen. */
    var measurementsTo: File? = null

    /**
     * A line has finished, one way or another.
     *
     * This runs on a binder thread -- the speech engine lives in another
     * process and calls back from wherever it likes. Everything it touches
     * that belongs to the player or the screen is therefore posted to the
     * main thread. Doing it directly throws inside the binder transaction,
     * where the exception is logged by the system and swallowed: the app
     * keeps running, the film keeps playing, and the only visible symptom
     * is that nothing after the offending line ever happens. It cost an
     * entire twelve-minute measurement run to notice.
     */
    private fun record(utteranceId: String?, how: String) {
        if (utteranceId == "warm-up") return
        val spokenMs = if (startedAtWall > 0) System.currentTimeMillis() - startedAtWall else -1
        log.append(utteranceId ?: "?").append('\t')
            .append(how).append('\t')
            .append(spokenMs).append('\t')
            .append(startedAtPosition).append('\t')
            .append(lastPositionMs).append('\n')
        if (how != "done") {
            Log.w(TAG, "Description at $utteranceId ended as $how after ${spokenMs}ms")
        }

        // Flushed after every line rather than at shutdown. A television
        // app is killed, not closed, and a measurement that only exists if
        // the process exits politely is a measurement nobody ever sees.
        measurementsTo?.let { file ->
            try {
                file.writeText(HEADER + log)
            } catch (error: Exception) {
                Log.w(TAG, "Could not write measurements: " + error.message)
            }
        }

        main.post {
            // Only the line that finished is cleared. By the time this runs
            // the next line may already have started; clearing it would give
            // the film its volume back mid-description and, worse, disarm
            // that line's hard stop.
            if (speaking?.startMs?.toString() == utteranceId) {
                speaking = null
                onSpeaking(null)
                onDuck(1f)
            }
        }
    }

    /**
     * Write down what every line actually took to say.
     *
     * This is the evidence, not a debug aid. A claim that no description
     * overlaps dialogue is only worth the measurement behind it, and the
     * only place the real duration of a real voice exists is here, on the
     * device, after it has finished speaking. `tools/calibrate.py` reads
     * this file back.
     */
    fun writeMeasurements(context: Context): File? {
        if (log.isEmpty()) return null
        val file = measurementsTo ?: File(context.filesDir, "spoken.tsv")
        return try {
            file.writeText("utterance\toutcome\tspoken_ms\tposition_ms\n$log")
            file
        } catch (error: Exception) {
            Log.w(TAG, "Could not write measurements: ${error.message}")
            null
        }
    }

    fun release(context: Context) {
        writeMeasurements(context)
        engine?.stop()
        engine?.shutdown()
        engine = null
        ready = false
    }

    private companion object {
        const val TAG = "SceneSpeak"
        const val HEADER = "utterance\toutcome\tspoken_ms\tposition_ms\tended_at_ms\n"
    }
}
