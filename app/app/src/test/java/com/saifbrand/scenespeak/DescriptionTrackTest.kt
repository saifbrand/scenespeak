package com.saifbrand.scenespeak

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * The player's half of the rule.
 *
 * The pipeline guarantees the track is safe; this decides what is spoken at
 * a given moment, and a mistake here would speak the wrong line at the
 * wrong time no matter how careful the track was.
 */
class DescriptionTrackTest {

    private val json = """
        {
          "film": "Test Film",
          "duration": 100.0,
          "lines": [
            {"start": 10.0, "budget": 5.0, "text": "First line.", "estimated_seconds": 2.0},
            {"start": 30.0, "budget": 4.0, "text": "Second line.", "estimated_seconds": 3.0},
            {"start": 50.0, "budget": 12.0, "text": "Third line.", "estimated_seconds": 9.0}
          ]
        }
    """.trimIndent()

    private val track = DescriptionTrack.parse(json)

    @Test
    fun `seconds on disk become milliseconds in the player`() {
        assertEquals(100_000L, track.durationMs)
        assertEquals(10_000L, track.lines[0].startMs)
        assertEquals(5_000L, track.lines[0].budgetMs)
        assertEquals(15_000L, track.lines[0].endMs)
    }

    @Test
    fun `a moment inside a slot finds its line`() {
        assertEquals("First line.", track.at(10_000)?.text)
        assertEquals("First line.", track.at(14_999)?.text)
        assertEquals("Third line.", track.at(55_000)?.text)
    }

    @Test
    fun `the moment a slot ends belongs to nobody`() {
        // Half-open on purpose: at exactly 15s the first line's time is up,
        // and something has to be the last instant it owns.
        assertNull(track.at(15_000))
    }

    @Test
    fun `a moment in the silence between slots finds nothing`() {
        assertNull(track.at(0))
        assertNull(track.at(20_000))
        assertNull(track.at(99_999))
    }

    @Test
    fun `lines arrive in order however the file listed them`() {
        val shuffled = DescriptionTrack.parse(
            """
            {"film":"f","duration":50.0,"lines":[
              {"start": 30.0, "budget": 2.0, "text": "later", "estimated_seconds": 1.0},
              {"start": 10.0, "budget": 2.0, "text": "earlier", "estimated_seconds": 1.0}
            ]}
            """.trimIndent()
        )
        assertEquals(listOf("earlier", "later"), shuffled.lines.map { it.text })
        assertEquals("earlier", shuffled.at(10_500)?.text)
    }

    @Test
    fun `an empty line is not a description`() {
        val withBlank = DescriptionTrack.parse(
            """
            {"film":"f","duration":50.0,"lines":[
              {"start": 10.0, "budget": 2.0, "text": "   ", "estimated_seconds": 1.0}
            ]}
            """.trimIndent()
        )
        assertEquals(0, withBlank.lines.size)
        assertNull(withBlank.at(10_500))
    }

    @Test
    fun `a track with no lines is valid and silent`() {
        val empty = DescriptionTrack.parse("""{"film":"f","duration":10.0,"lines":[]}""")
        assertEquals(0, empty.lines.size)
        assertNull(empty.at(5_000))
    }

    @Test
    fun `a missing lines array is not a crash`() {
        val none = DescriptionTrack.parse("""{"film":"f","duration":10.0}""")
        assertEquals(0, none.lines.size)
    }

    @Test
    fun `the search finds every line in a long track`() {
        val many = (0 until 500).joinToString(",") { index ->
            """{"start": ${index * 10}.0, "budget": 4.0, "text": "line $index",
               "estimated_seconds": 2.0}"""
        }
        val long = DescriptionTrack.parse("""{"film":"f","duration":5000.0,"lines":[$many]}""")
        for (index in 0 until 500) {
            assertEquals("line $index", long.at(index * 10_000L + 1_000)?.text)
            assertNull(long.at(index * 10_000L + 5_000))
        }
    }

    @Test
    fun `a track without a language is english`() {
        assertEquals("en", track.language)
    }

    @Test
    fun `a track carries its language to the voice`() {
        val bengali = DescriptionTrack.parse("""{"film":"f","duration":10.0,"language":"bn","lines":[]}""")
        assertEquals("bn", bengali.language)
    }
}
