import re

# ASCII escapes keep this source file independent of terminal encoding.
MOJIBAKE_MARKERS = (
    "\u00c3",  # UTF-8 accents decoded as Windows-1252 (for example, Ã©)
    "\u00c2",
    "\u00e2\u20ac",  # Curly punctuation (for example, â€™)
    "\u00f0\u0178",  # Emoji bytes decoded as Windows-1252
)


def _mojibake_score(value: str) -> int:
    return sum(value.count(marker) for marker in MOJIBAKE_MARKERS)


def _repair_token(token: str) -> str:
    repaired = token

    # Two passes also handle text that was accidentally encoded twice.
    for _ in range(2):
        if _mojibake_score(repaired) == 0:
            break

        try:
            candidate = repaired.encode("windows-1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break

        if _mojibake_score(candidate) >= _mojibake_score(repaired):
            break

        repaired = candidate

    return repaired


def repair_utf8_mojibake(value: str) -> str:
    """Repair UTF-8 text mistakenly decoded as Windows-1252."""

    # Repair individual non-whitespace tokens. A real emoji or correctly
    # decoded accented word elsewhere must not prevent a bad token from
    # being repaired.
    return "".join(
        part if part.isspace() else _repair_token(part)
        for part in re.split(r"(\s+)", value)
    )
