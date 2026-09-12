package com.saifbrand.scenespeak

import org.json.JSONObject

/**
 * One spoken description and the silence it was written for.
 *
 * [budgetMs] is not advice. It is the length of the gap in the film's
 * dialogue that this line was measured against, and the narrator stops
 * speaking when it runs out, whatever is left unsaid.
 */
data class Description(
    val startMs: Long,
    val budgetMs: Long,
    val text: String,
    val estimatedMs: Long,
) {
    val endMs: Long get() = startMs + budgetMs
}

/**
 * A film's complete description track, as produced by the `describe`
 * pipeline and carried alongside the film.
 */
class DescriptionTrack(
    val film: String,
    val durationMs: Long,
    val lines: List<Description>,
) {
    /**
     * The line that should be speaking at [positionMs], if any.
     *
     * A linear scan would be fine for the few dozen lines a film has, but
     * this is called several times a second for the whole running time, so
     * it binary-searches instead and the player stays smooth on a stick
     * with a slow CPU.
     */
    fun at(positionMs: Long): Description? {
        var low = 0
        var high = lines.size - 1
        while (low <= high) {
            val middle = (low + high) / 2
            val line = lines[middle]
            when {
                positionMs < line.startMs -> high = middle - 1
                positionMs >= line.endMs -> low = middle + 1
                else -> return line
            }
        }
        return null
    }

    companion object {
        /**
         * Read a track from the JSON the pipeline writes.
         *
         * Seconds on disk, milliseconds in the player: the pipeline works
         * in seconds because that is what subtitles and ffmpeg speak, and
         * ExoPlayer reports milliseconds. Converting once, here, keeps the
         * rest of the app in one unit.
         */
        fun parse(json: String): DescriptionTrack {
            val root = JSONObject(json)
            val items = root.optJSONArray("lines")
            val lines = ArrayList<Description>(items?.length() ?: 0)
            for (index in 0 until (items?.length() ?: 0)) {
                val item = items!!.getJSONObject(index)
                val text = item.optString("text").trim()
                if (text.isEmpty()) continue
                lines.add(
                    Description(
                        startMs = (item.getDouble("start") * 1000).toLong(),
                        budgetMs = (item.getDouble("budget") * 1000).toLong(),
                        text = text,
                        estimatedMs = (item.optDouble("estimated_seconds", 0.0) * 1000).toLong(),
                    )
                )
            }
            lines.sortBy { it.startMs }
            return DescriptionTrack(
                film = root.optString("film", "Unknown film"),
                durationMs = (root.optDouble("duration", 0.0) * 1000).toLong(),
                lines = lines,
            )
        }
    }
}
