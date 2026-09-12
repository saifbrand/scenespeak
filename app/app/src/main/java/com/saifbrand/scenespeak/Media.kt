package com.saifbrand.scenespeak

import android.Manifest
import android.content.ContentUris
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import android.util.Log
import androidx.core.content.ContextCompat

/**
 * Finding the film to play, and the track that describes it.
 *
 * This is more code than "open the file" because Android stopped allowing
 * that. From Android 11 -- which is Fire OS 8 -- an app cannot read an
 * ordinary path under `/sdcard`, and the app's own external directory
 * cannot be written to over `adb push` on a production image, so neither of
 * the two obvious approaches works on a Fire TV stick. The one that does is
 * MediaStore: the film goes in the public Movies folder like any other
 * video, and the app asks the system for it by name.
 *
 * The track is different. It is a few kilobytes, it belongs to the app, and
 * MediaStore has no place to keep a JSON file, so it ships inside the APK.
 */
object Media {

    /** Where a person is told to put the film. */
    const val PUBLIC_FOLDER = "/sdcard/Movies/scenespeak"

    /** The permission needed to read somebody else's video file. */
    val PERMISSION: String =
        if (Build.VERSION.SDK_INT >= 33) Manifest.permission.READ_MEDIA_VIDEO
        else Manifest.permission.READ_EXTERNAL_STORAGE

    /** The film that ships inside the APK, so the app works on its own. */
    const val BUILT_IN = "asset:///film.mp4"

    data class Found(val film: Uri, val name: String, val trackJson: String)

    fun granted(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, PERMISSION) ==
            PackageManager.PERMISSION_GRANTED

    /**
     * What to play: a film the viewer supplied, or the one in the APK.
     *
     * The built-in copy is what makes this demo-ready rather than
     * demo-shaped. Install the APK on a stick with nothing else on it and
     * there is a film, a description track written for that film, and a
     * voice reading it -- no sideloaded media, no permission, no setup.
     */
    fun find(context: Context): Found =
        supplied(context) ?: Found(Uri.parse(BUILT_IN), "Tears of Steel", track(context))

    /**
     * The first video in the scenespeak folder, or any video at all.
     *
     * Falling back to "any video on the device" is deliberate. A viewer who
     * has sideloaded one film to try this with should not have to discover
     * that it needed to be in a particular directory.
     */
    fun supplied(context: Context): Found? {
        if (!granted(context)) return null

        val columns = arrayOf(
            MediaStore.Video.Media._ID,
            MediaStore.Video.Media.DISPLAY_NAME,
            MediaStore.Video.Media.RELATIVE_PATH,
        )
        val collection = MediaStore.Video.Media.EXTERNAL_CONTENT_URI

        var best: Pair<Uri, String>? = null
        val found = try {
            context.contentResolver.query(
                collection, columns, null, null,
                MediaStore.Video.Media.DISPLAY_NAME + " ASC",
            )
        } catch (error: SecurityException) {
            Log.i("SceneSpeak", "No access to the media library: " + error.message)
            null
        }
        found?.use { cursor ->
            val idColumn = cursor.getColumnIndexOrThrow(MediaStore.Video.Media._ID)
            val nameColumn = cursor.getColumnIndexOrThrow(MediaStore.Video.Media.DISPLAY_NAME)
            val pathColumn = cursor.getColumnIndex(MediaStore.Video.Media.RELATIVE_PATH)
            while (cursor.moveToNext()) {
                val uri = ContentUris.withAppendedId(collection, cursor.getLong(idColumn))
                val name = cursor.getString(nameColumn) ?: continue
                val path = if (pathColumn >= 0) cursor.getString(pathColumn).orEmpty() else ""
                if (path.contains("scenespeak", ignoreCase = true)) {
                    return Found(uri, name, track(context))
                }
                if (best == null) best = uri to name
            }
        }
        return best?.let { (uri, name) -> Found(uri, name, track(context)) }
    }

    private fun track(context: Context): String =
        context.assets.open("track.json").bufferedReader().use { it.readText() }
}
