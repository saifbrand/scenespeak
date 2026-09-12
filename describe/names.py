"""Stop a description naming somebody the film has not named yet.

A sighted viewer learns a character's name when another character says it.
A described viewer must learn it at the same moment and not before. This is
not a small point of etiquette: a description that says "Vesper reaches for
the syringe" before anyone says "Vesper" has handed the listener information
the film was withholding -- a spoiler delivered by the accessibility feature
itself.

A model writing from frames is particularly prone to it, because a well
known film's character names are in its training data. Measured on Tears of
Steel, the writer used "Vesper" -- a name that appears nowhere in the
subtitles at any point -- in a line placed at 6:51. So this is enforced
rather than requested.

The hard part is telling a name from an ordinary capitalised word, because
every sentence starts with a capital letter and most of those are "The".
Two rules do it between them:

1. A capitalised word that is *not* at the start of a sentence is a name.
   "He hands it to Barley" can only be a name.
2. A word at the start of a sentence is a name only if the film's own
   dialogue uses that word capitalised mid-sentence somewhere. That is how
   the cast list is learned from the film instead of being guessed at, and
   it is why "Smoke fills the room" is left alone.

The second rule is a backstop with a known limit: a name the film never
says at all, used as the first word of a description, is invisible to it.
The writer is told the rule as well, so this is the second line of defence
rather than the only one.
"""
from __future__ import annotations

import re

from describe.subtitles import Cue

WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
SENTENCE_START = re.compile(r"(?:^|[.!?]\s+|[\"(\[]\s*)$")

# Capitalised words that are not names: sentence openers, days and months,
# and the handful of proper-ish nouns that carry no information about who
# anybody is.
NOT_A_NAME = frozenset("""
a an the and or but if so as at by for from in into of on onto over to with
he she it they them their his her its this that these those there here then
who what when where why how one two three four five six seven eight nine ten
i i'm i'll i've we we're you your yours yes no not never nothing something
monday tuesday wednesday thursday friday saturday sunday
january february march april may june july august september october
november december earth sun moon
""".split())


def _bare(word: str) -> str:
    """A word without its possessive ending, lowercased."""
    return re.sub(r"'s$", "", word.lower())


def cast(cues: list[Cue]) -> set[str]:
    """Names the film's dialogue uses, learned from the dialogue itself.

    Only mid-sentence capitals count here. A subtitle beginning "Thom." also
    names him, but a subtitle beginning "Smoke." would enrol a weather
    condition in the cast, and the cost of that mistake is a description
    needlessly thrown away.
    """
    found: set[str] = set()
    for cue in cues:
        for match in WORD.finditer(cue.text):
            word = match.group(0)
            if not word[:1].isupper() or _bare(word) in NOT_A_NAME:
                continue
            if SENTENCE_START.search(cue.text[:match.start()]):
                continue
            found.add(_bare(word))
    return found


def proper_nouns(text: str, known_cast: set[str] | None = None) -> set[str]:
    """Words in a description that name a person."""
    known_cast = known_cast or set()
    found: set[str] = set()
    for match in WORD.finditer(text):
        word = match.group(0)
        if not word[:1].isupper() or _bare(word) in NOT_A_NAME:
            continue
        if SENTENCE_START.search(text[:match.start()]):
            # Only a word the film itself uses as a name counts here.
            if _bare(word) in known_cast:
                found.add(word)
            continue
        found.add(word)
    return found


def introduced_by(cues: list[Cue], when: float) -> set[str]:
    """Every name the dialogue has spoken aloud by `when`.

    Sentence-initial words do count here, unlike anywhere else: subtitles
    routinely open with a name -- "Thom. Listen to me." -- and if the film
    has said it, the listener has already heard it.
    """
    known: set[str] = set()
    for cue in cues:
        if cue.end > when:
            break
        for match in WORD.finditer(cue.text):
            word = match.group(0)
            if word[:1].isupper() and _bare(word) not in NOT_A_NAME:
                known.add(_bare(word))
    return known


def leaks(text: str, cues: list[Cue], when: float) -> set[str]:
    """Names this line gives away before the film gives them away."""
    known = introduced_by(cues, when)
    return {word for word in proper_nouns(text, cast(cues))
            if _bare(word) not in known}
