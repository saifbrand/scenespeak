package com.saifbrand.scenespeak

import android.os.Bundle
import android.view.KeyEvent
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import androidx.tv.material3.Text
import kotlinx.coroutines.delay

/**
 * SceneSpeak on Fire TV.
 *
 * The whole app is one screen, because the feature is one thing: play the
 * film, and speak what a blind viewer cannot see, into the gaps where
 * nobody is talking. The remote's play/pause and the D-pad centre toggle
 * description on and off; there is no menu to get lost in.
 */
class MainActivity : ComponentActivity() {

    private var player: ExoPlayer? = null
    private var narrator: Narrator? = null

    /**
     * Whether descriptions are being spoken.
     *
     * It lives on the activity rather than inside the composable because
     * the remote arrives at `onKeyDown`, outside composition. Being Compose
     * state, writing it from there still redraws the screen.
     */
    private var describing by mutableStateOf(true)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { SceneSpeakScreen() }
    }

    override fun onDestroy() {
        narrator?.release(this)
        player?.release()
        super.onDestroy()
    }

    @Composable
    private fun SceneSpeakScreen() {
        val context = this
        // No permission is asked for on launch. The film is in the APK, so
        // the app has everything it needs; a viewer who has put their own
        // film on the device grants access in Settings and it is picked up
        // instead. Opening with a permission dialog for a feature the app
        // does not need yet is how accessibility apps get uninstalled.
        val media = remember { Media.find(context) }
        if (media == null) {
            NoFilm()
            return
        }

        val track = remember { DescriptionTrack.parse(media.trackJson) }
        var saying by remember { mutableStateOf<Description?>(null) }
        var position by remember { mutableStateOf(0L) }

        val exo = remember {
            ExoPlayer.Builder(context).build().apply {
                setMediaItem(MediaItem.fromUri(media.film))
                prepare()
                playWhenReady = true
            }.also { player = it }
        }

        val voice = remember {
            Narrator(
                context = context,
                onSpeaking = { saying = it },
                onDuck = { volume -> exo.volume = volume },
            ).also {
                // Internal storage, not external. On Android 11 the app's own
                // external directory cannot be read back over adb on a
                // production image, and a measurement that cannot be got off
                // the device is not evidence of anything.
                it.measurementsTo = java.io.File(filesDir, "spoken.tsv")
                it.language = track.language
                narrator = it
            }
        }
        voice.enabled = describing

        // The film's own clock drives everything. Ten ticks a second: a
        // line may only start if what is left of its slot still fits it,
        // so a slow poll does not merely delay a description, it throws it
        // away. At four ticks a second two lines of this film were lost
        // that way. Ten is still nothing next to decoding video.
        LaunchedEffect(exo) {
            while (true) {
                position = exo.currentPosition
                voice.update(track, position, exo.isPlaying)
                delay(100)
            }
        }

        DisposableEffect(Unit) {
            onDispose {
                voice.release(context)
                exo.release()
            }
        }

        Box(Modifier.fillMaxSize().background(Color.Black)) {
            AndroidView(
                modifier = Modifier.fillMaxSize(),
                factory = { ctx ->
                    PlayerView(ctx).apply {
                        this.player = exo
                        useController = false
                        // The remote is the controller. An overlay of
                        // buttons is no use to the viewer this is built for.
                        isFocusable = false
                    }
                },
            )

            Overlay(track = track, saying = saying, position = position)
        }
    }

    /**
     * The remote. Centre toggles description, play/pause does both, and
     * everything else is left to the system.
     */
    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        val exo = player ?: return super.onKeyDown(keyCode, event)
        return when (keyCode) {
            KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> {
                describing = !describing
                narrator?.enabled = describing
                true
            }
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, KeyEvent.KEYCODE_SPACE -> {
                exo.playWhenReady = !exo.playWhenReady; true
            }
            KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_MEDIA_FAST_FORWARD -> {
                exo.seekTo(exo.currentPosition + 30_000); narrator?.seeked(); true
            }
            KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_MEDIA_REWIND -> {
                exo.seekTo(maxOf(0, exo.currentPosition - 30_000)); narrator?.seeked(); true
            }
            else -> super.onKeyDown(keyCode, event)
        }
    }

    @Composable
    private fun Overlay(
        track: DescriptionTrack,
        saying: Description?,
        position: Long,
    ) {
        Column(
            modifier = Modifier.fillMaxSize().padding(48.dp),
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top,
            ) {
                Text(
                    text = track.film,
                    color = Color.White.copy(alpha = 0.75f),
                    fontSize = 20.sp,
                )
                Text(
                    text = if (describing) "Description ON" else "Description OFF",
                    color = if (describing) Color(0xFF7CE1B0) else Color.White.copy(alpha = 0.5f),
                    fontSize = 20.sp,
                    fontWeight = FontWeight.Medium,
                )
            }

            // The spoken line is also shown. It is not needed by the viewer
            // this is built for, but it is how a sighted person -- a family
            // member, a reviewer, a judge -- can see that the thing being
            // said matches the thing on screen.
            if (saying != null) {
                Text(
                    text = saying.text,
                    color = Color.White,
                    fontSize = 28.sp,
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(Color.Black.copy(alpha = 0.55f))
                        .padding(20.dp),
                )
            } else {
                Text(
                    text = clock(position, track.durationMs),
                    color = Color.White.copy(alpha = 0.35f),
                    fontSize = 18.sp,
                )
            }
        }
    }

    /**
     * Shown when the APK was built without its film.
     *
     * The film is not in the repository — it is 55 MB of somebody else's
     * work — so an APK built straight from a fresh clone has only the track.
     * A black screen would look like a crash; this says what happened.
     */
    @Composable
    private fun NoFilm() {
        Box(Modifier.fillMaxSize().background(Color.Black), Alignment.Center) {
            Text(
                text = "This build has no film.\n\nRun tools/fetch_media.sh, rebuild, and install " +
                    "again — or copy a video into " + Media.PUBLIC_FOLDER +
                    " and allow SceneSpeak to read it in Settings.",
                color = Color.White,
                fontSize = 28.sp,
                modifier = Modifier.padding(96.dp),
            )
        }
    }
}

private fun clock(positionMs: Long, durationMs: Long): String {
    fun stamp(ms: Long) = "%d:%02d".format(ms / 60000, (ms / 1000) % 60)
    return stamp(positionMs) + " / " + stamp(durationMs)
}
