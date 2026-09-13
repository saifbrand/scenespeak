"""Write the line that goes in one slot, from the pictures in it.

Audio description is a written craft with rules, and most of the quality of
this program lives in the instructions below rather than in any code. The
rules are the ones described service providers work to: present tense, only
what is visible, never repeat what the dialogue already said, and never
name a character the film has not named yet -- a listener who is told "Thom"
before the film says it has been handed a spoiler, not a description.

The writer is an interface with more than one implementation on purpose. A
hackathon entry that only runs against one vendor's endpoint is a demo of
that vendor; the pipeline should be able to write with whatever the person
running it has, including nothing at all.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from describe import speech

GUIDANCE = """You write audio description for blind and low-vision viewers.

You will be shown frames sampled in order from one silent gap in a film, and
you write the single line that is spoken aloud during that gap.

Rules:
- Present tense. Third person. No "we see", no "the camera", no "the scene".
- Describe only what is visible. Never explain, interpret motive, or name an
  emotion that is not on a face.
- Never repeat information the dialogue already gives. The listener hears the
  dialogue; your job is the picture.
- Refer to people by what can be seen -- "a woman in a leather jacket" --
  unless the dialogue quoted below has already named them, in which case use
  the name.
- If the frames differ, describe the change, not each frame in turn.
- If nothing worth describing happens, answer exactly: SKIP
- One sentence. No quotation marks, no preamble, no markdown."""


@dataclass
class Request:
    """Everything the writer is told about one slot."""

    start: float
    budget: float
    shots: list[str]
    """Paths to the sampled frames, in time order."""

    before: list[str] = field(default_factory=list)
    """The last lines of dialogue heard before this gap."""
    after: list[str] = field(default_factory=list)
    """The lines that follow it, so the description does not pre-empt them."""
    said_already: list[str] = field(default_factory=list)
    """Descriptions already spoken, so this one does not repeat them."""
    too_long: str = ""
    """A previous answer that would not fit. Asking for a shorter line and
    being told why produces a real sentence; cutting words off the end of
    the long one produces "two figures stand in a complex industrial"."""
    forbidden: list[str] = field(default_factory=list)
    """Names the writer used that the film has not said out loud yet."""
    language: str = "en"
    """What to write in. Audio description barely exists outside English,
    and the film's own dialogue is not required to be in the same language
    as the description -- a Bengali viewer may well be watching an English
    film with Bengali description over it."""

    def prompt(self, calibration: speech.Calibration) -> str:
        words = speech.words_for(self.budget, calibration)
        parts = [
            f"The gap is {self.budget:.1f} seconds long, which is about "
            f"{words} words when spoken aloud. Do not exceed it.",
        ]
        if self.language and self.language.split("-")[0].lower() != "en":
            parts.append(
                f"Write the line in {LANGUAGES.get(self.language.split('-')[0].lower(), self.language)}"
                " and in that language's own script. The dialogue quoted"
                " below stays in the film's language; do not translate it"
                " back to the listener, and do not add any English.")
        if self.before:
            parts.append("Dialogue just before this gap:\n"
                         + "\n".join(f"- {line}" for line in self.before[-3:]))
        if self.after:
            parts.append("Dialogue immediately after it (do not pre-empt it):\n"
                         + "\n".join(f"- {line}" for line in self.after[:2]))
        if self.too_long:
            parts.append(
                "Your previous answer was too long to speak in the time:\n"
                f"- {self.too_long}\n"
                "Write a shorter one. Say less, do not abbreviate, and do "
                "not end mid-phrase.")
        if self.forbidden:
            parts.append(
                "Do not use these names -- nobody in the film has said them "
                "yet, and the listener must not learn them before a sighted "
                "viewer would: " + ", ".join(sorted(self.forbidden))
                + ".\nDescribe the person by what can be seen instead.")
        if self.said_already:
            parts.append("Already described earlier, do not repeat:\n"
                         + "\n".join(f"- {line}" for line in self.said_already[-4:]))
        return "\n\n".join(parts)


# Named so the request reads as a sentence rather than a language tag. Only
# the ones a Fire TV text-to-speech engine actually has a voice for are
# worth offering, which is checked on the device, not assumed here.
LANGUAGES = {
    "bn": "Bengali", "hi": "Hindi", "ur": "Urdu", "ta": "Tamil",
    "es": "Spanish", "fr": "French", "de": "German", "it": "Italian",
    "pt": "Portuguese", "ru": "Russian", "ar": "Arabic", "id": "Indonesian",
    "ja": "Japanese", "ko": "Korean", "zh": "Chinese", "tr": "Turkish",
    "nl": "Dutch", "pl": "Polish", "th": "Thai", "vi": "Vietnamese",
}


class StubWriter:
    """A writer that invents nothing and needs no network.

    Used by the tests and by `--writer stub`, so that the placement, timing
    and verification can be exercised end to end without a key. It returns a
    line sized to the slot, which is exactly what the rest of the pipeline
    has to cope with.
    """

    name = "stub"

    def write(self, request: Request) -> str:
        words = max(3, speech.words_for(request.budget))
        filler = ["A figure", "moves", "through", "the", "room", "as", "light",
                  "shifts", "across", "the", "wall", "and", "the", "doors",
                  "close", "behind", "them"]
        return " ".join((filler * 4)[:words]).rstrip(",") + "."


class GeminiWriter:
    """Google's Gemini, spoken to over plain HTTP with no SDK.

    Standard library only, for the same reason the rest of the project is:
    a judge or a maintainer can read every line that leaves this machine.
    """

    ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
                "{model}:generateContent")

    def __init__(self, api_key: str = "", model: str = "",
                 fallback: str = "gemini-flash-lite-latest",
                 calibration: speech.Calibration = speech.Calibration(),
                 every: float = 4.5):
        self.api_key = api_key or os.environ.get("SCENESPEAK_GEMINI_KEY", "")
        if not self.api_key:
            raise RuntimeError(
                "No model key. Set SCENESPEAK_GEMINI_KEY, or run with "
                "--writer stub to exercise the pipeline without one."
            )
        self.model = model or os.environ.get("SCENESPEAK_MODEL",
                                             "gemini-flash-lite-latest")
        self.fallback = fallback
        self.calibration = calibration
        # A free-tier key is limited per minute, not only per day. Pacing the
        # requests is what turns a 48-slot film from a run that dies halfway
        # into one that finishes; the cache means a death halfway is cheap,
        # but it is still a run nobody can reproduce in one go.
        self.every = float(os.environ.get("SCENESPEAK_INTERVAL", every))
        self._last = 0.0

    def _wait_turn(self) -> None:
        gap = self.every - (time.monotonic() - self._last)
        if gap > 0:
            time.sleep(gap)
        self._last = time.monotonic()

    @property
    def name(self) -> str:
        return f"gemini:{self.model}"

    def write(self, request: Request) -> str:
        parts: list[dict] = [{"text": request.prompt(self.calibration)}]
        for path in request.shots:
            with open(path, "rb") as handle:
                parts.append({"inline_data": {
                    "mime_type": "image/jpeg",
                    "data": base64.b64encode(handle.read()).decode("ascii"),
                }})
        body = {
            "system_instruction": {"parts": [{"text": GUIDANCE}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 20000},
        }
        return _one_line(self._post(self.model, body))

    def _post(self, model: str, body: dict, attempt: int = 0) -> str:
        request = urllib.request.Request(
            self.ENDPOINT.format(model=model),
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "x-goog-api-key": self.api_key},
        )
        self._wait_turn()
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:600].decode("utf-8", "replace")
            if exc.code in (429, 500, 502, 503) and attempt < 5:
                # The server says how long to wait when it knows. Guessing
                # shorter than it asked for is how a run gets itself banned
                # for the rest of the day.
                time.sleep(max(_retry_after(detail), 2 ** attempt))
                return self._post(model, body, attempt + 1)
            # A spent daily quota on one model does not mean the key is dead:
            # the quota is counted per model, so the smaller one is tried
            # before giving up on the run.
            if exc.code == 429 and model != self.fallback:
                return self._post(self.fallback, body)
            raise RuntimeError(
                f"{model} refused the request: {exc.code} {detail[:300]}"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < 5:
                time.sleep(2 ** attempt)
                return self._post(model, body, attempt + 1)
            raise RuntimeError(f"{model} could not be reached: {exc}") from exc

        for candidate in payload.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                if part.get("text"):
                    return part["text"]
        return ""


def _retry_after(detail: str) -> float:
    """How long the server asked us to wait, from its own error body."""
    match = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', detail)
    return float(match.group(1)) + 1 if match else 0.0


QUOTES = '"“”‘’'


def _one_line(text: str) -> str:
    """Reduce whatever came back to a single spoken sentence."""
    cleaned = " ".join(text.split()).strip().strip(QUOTES)
    for prefix in ("Description:", "Audio description:", "Line:"):
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix):].strip()
    return cleaned.strip(QUOTES)
