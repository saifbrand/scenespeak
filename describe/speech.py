"""How long a line takes to say out loud.

A description is written against a budget in seconds, but a language model
writes words, not seconds. Something has to convert between the two before
the line is committed to the track, because discovering that a line is too
long while the film is playing is too late.

The estimate here is deliberately conservative and it is *calibrated, not
guessed*: `calibrate.py` speaks a set of lines through the same Android
text-to-speech engine the player uses, measures the audio it produces, and
fits the constants below to what was actually measured. The player still
hard-stops the voice at the end of its slot, so the estimate decides how
much gets said, never whether the rule is kept.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass

# Languages whose syllables the counter below can honestly claim to count.
# Everything else is timed by glyph, which is cruder and honest about it.
LATIN_ENOUGH = frozenset({"en"})

VOWELS = re.compile(r"[aeiouy]+")
WORDS = re.compile(r"[A-Za-z']+")
CLAUSE = re.compile(r"(?<=[,;:.।])\s+")   # । is the Indic full stop

# Anything that is spoken, in any script: letters, no spaces, digits or
# punctuation. Used to time a language whose syllables this module has no
# business claiming to count.
GLYPHS = re.compile(r"[^\W\d_]", re.UNICODE)

# Marks that hang off a letter rather than being one: Bengali vowel signs,
# Arabic harakat, Thai tone marks, Latin accents. They change how a letter
# sounds without adding a beat to it, so they are not counted.
COMBINING = re.compile(
    "["
    "̀-ͯ"    # Latin and Greek accents
    "҃-҉"    # Cyrillic
    "֑-ֽ"    # Hebrew points
    "ً-ٟ"    # Arabic harakat
    "ঁ-ঃ়া-্ৗ"   # Bengali signs and virama
    "ँ-ः़ा-्॑-ॗ"   # Devanagari
    "ัิ-ฺ็-๎"         # Thai
    "]"
)

# Words a phrase hangs from. Cutting a sentence at one of these, and
# removing it, leaves the head of the sentence intact and readable.
CONNECTORS = frozenset("""
before after as while with into onto through across toward towards behind
beneath beside between beyond under over against among around during past
and but or then where which who that
""".split())

# Words that cannot end a description. Cutting after one of them leaves a
# sentence hanging on nothing -- "swallowed by a" -- which is worse than the
# shorter line that stops before it.
DANGLING = frozenset("""
a an the and or but of to in on at by for with from into onto over under
his her its their my your our is are was were be been being as that than
""".split())


@dataclass(frozen=True)
class Calibration:
    """Constants of the duration model, in seconds.

    A synthesiser's cost is roughly a fixed start-up plus a cost per
    syllable, with punctuation buying a pause. Syllables beat words because
    "extraordinarily" and "cat" are both one word and nothing alike.
    """

    overhead: float = 0.28
    """Engine start-up before the first sound, plus the trailing silence
    every synthesiser leaves at the end of an utterance."""

    per_syllable: float = 0.196
    per_pause: float = 0.22
    """Extra time bought by a comma, semicolon, colon or full stop."""

    safety: float = 1.08
    """Everything is multiplied by this. A line that finishes early costs
    nothing; a line that finishes late talks over an actor."""

    source: str = "default"
    """Where these numbers came from — "default", or the device and voice
    they were measured on, so a published figure can be traced."""

    language: str = "en"
    """The language these constants were measured for.

    Speech rate is not a property of the synthesiser alone. The same engine
    reading Bengali and English covers different amounts of meaning per
    second, and the unit being counted is not even the same thing, so a
    track in a new language needs its own measured constants — obtained the
    same way as the English ones, by being spoken on the device and timed.
    """

    @property
    def counts_syllables(self) -> bool:
        """Whether the syllable counter applies to this language at all.

        It is an English heuristic — vowel groups, silent final e — and
        pretending it generalises would be worse than admitting it does
        not. For everything else the unit is a written glyph, which is
        cruder but is a real proportional measure of how much there is to
        say, and the constant in front of it is measured rather than
        assumed.
        """
        return self.language.split("-")[0].lower() in LATIN_ENOUGH

    @classmethod
    def load(cls, path: str = "") -> "Calibration":
        path = path or os.environ.get("SCENESPEAK_CALIBRATION", "calibration.json")
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return cls()
        known = {field: data[field] for field in asdict(cls()) if field in data}
        return cls(**known)


def syllables(word: str) -> int:
    """Count syllables in one English word, well enough to time it.

    An approximation, and it does not need to be better than one: the safety
    factor and the player's hard stop both sit downstream of it.
    """
    word = word.lower()
    groups = VOWELS.findall(word)
    count = len(groups)
    if count > 1 and word.endswith("e") and not word.endswith(("le", "ee", "ye")):
        count -= 1
    return max(1, count)


def beats(text: str, calibration: Calibration = Calibration()) -> int:
    """How many units of speech this line contains.

    Syllables where they can honestly be counted, written glyphs where they
    cannot. Either way the unit only has to be *proportional* to the time
    the line takes: what converts units into seconds is a constant measured
    on the device, per language.
    """
    if calibration.counts_syllables:
        return sum(syllables(word) for word in WORDS.findall(text))
    return len(GLYPHS.findall(COMBINING.sub("", text)))


def duration(text: str, calibration: Calibration = Calibration()) -> float:
    """Seconds this line will take to speak."""
    units = beats(text, calibration)
    if not units:
        return 0.0
    pauses = len(re.findall(r"[,;:.।](?:\s|$)", text))
    spoken = (calibration.overhead
              + units * calibration.per_syllable
              + pauses * calibration.per_pause)
    return round(spoken * calibration.safety, 3)


def words_for(budget: float, calibration: Calibration = Calibration()) -> int:
    """Roughly how many words fit in a budget, for asking a model.

    Used only to phrase the request — "about nine words" reads better to a
    language model than "2.4 seconds", and a number it can count against
    makes it far more likely to come back with something that fits. The
    answer is still measured afterwards.
    """
    usable = budget / calibration.safety - calibration.overhead
    units = max(0.0, usable) / calibration.per_syllable
    # About 1.55 syllables per English word in plain prose; about 4.4
    # glyphs per word in a Bengali sentence. Both are rules of thumb used
    # only to phrase the request, never to decide whether a line fits.
    per_word = 1.55 if calibration.counts_syllables else 4.4
    return max(1, int(units / per_word))


def fits(text: str, budget: float, calibration: Calibration = Calibration()) -> bool:
    return duration(text, calibration) <= budget


def trim(text: str, budget: float,
         calibration: Calibration = Calibration()) -> str:
    """Shorten a line until it fits, or give up and return nothing.

    Whole clauses are dropped from the end first, because a description cut
    at a clause boundary is still a sentence someone can follow. Only if the
    first clause alone is already too long does it fall back to dropping
    words, and a line reduced below three words is abandoned: "A man" tells
    a listener nothing and spends a slot that the next description could
    have used.
    """
    if fits(text, budget, calibration):
        return text

    parts = CLAUSE.split(text.strip())
    while len(parts) > 1:
        parts.pop()
        candidate = " ".join(parts).rstrip(" ,;:")
        if not candidate.endswith("."):
            candidate += "."
        if fits(candidate, budget, calibration):
            return candidate

    words = (parts[0] if parts else text).split()

    # Cut at a phrase boundary rather than mid-phrase. Truncating at the
    # last connector and dropping it too turns "figures stand before a
    # glowing control interface" into "figures stand", which is a sentence;
    # dropping words off the end turns it into "figures stand before a
    # glowing control", which is not.
    for index in range(len(words) - 1, 2, -1):
        if words[index].strip(",;:.").lower() not in CONNECTORS:
            continue
        candidate = " ".join(words[:index]).rstrip(" ,;:") + "."
        if len(candidate.split()) >= 3 and fits(candidate, budget, calibration):
            return candidate

    while len(words) > 3:
        words.pop()
        while len(words) > 3 and words[-1].strip(",;:.").lower() in DANGLING:
            words.pop()
        candidate = " ".join(words).rstrip(" ,;:") + "."
        if fits(candidate, budget, calibration):
            return candidate
    return ""
