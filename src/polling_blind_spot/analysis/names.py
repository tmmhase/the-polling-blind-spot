"""Match poll candidate names to official return names.

The comparison uses the published strings only. It does not consult vote
totals, and it does not apply a list of individual people. A last-name edit
such as O'CONNER versus O'CONNOR stays unmatched.
"""

from __future__ import annotations

import re
import unicodedata

_TITLES = {"DR", "MR", "MRS", "MS", "HON", "SEN"}
_SUFFIXES = {"JR", "SR", "II", "III", "IV"}
_NAME_GROUPS = (
    frozenset({"ROBERT", "BOB", "ROB", "ROBBY", "BOBBY"}),
    frozenset({"WILLIAM", "BILL", "BILLY", "WILL", "WILLIE"}),
    frozenset({"JAMES", "JIM", "JIMMY", "JAMIE"}),
    frozenset({"THOMAS", "TOM", "TOMMY", "THOM"}),
    frozenset({"RICHARD", "RICK", "RICKY", "DICK"}),
    frozenset({"CHARLES", "CHUCK", "CHARLIE", "CHAS"}),
    frozenset({"JOSEPH", "JOE", "JOEY"}),
    frozenset({"MICHAEL", "MIKE", "MICKEY"}),
    frozenset({"DANIEL", "DAN", "DANNY"}),
    frozenset({"DAVID", "DAVE"}),
    frozenset({"STEVEN", "STEPHEN", "STEVE"}),
    frozenset({"ANTHONY", "TONY"}),
    frozenset({"NICHOLAS", "NICK"}),
    frozenset({"CHRISTOPHER", "CHRIS"}),
    frozenset({"MATTHEW", "MATT"}),
    frozenset({"ANDREW", "ANDY", "DREW"}),
    frozenset({"JONATHAN", "JON"}),
    frozenset({"BENJAMIN", "BEN", "BENNY"}),
    frozenset({"SAMUEL", "SAM"}),
    frozenset({"ALEXANDER", "ALEX"}),
    frozenset({"NATHANIEL", "NATE"}),
    frozenset({"PATRICK", "PAT"}),
    frozenset({"EDWARD", "ED", "TED", "TEDDY"}),
    frozenset({"THEODORE", "TED", "TEDDY"}),
    frozenset({"DOUGLAS", "DOUG"}),
    frozenset({"LOUIS", "LOU"}),
    frozenset({"LAWRENCE", "LARRY"}),
    frozenset({"GERALD", "JERRY"}),
    frozenset({"RAYMOND", "RAY"}),
    frozenset({"DONALD", "DON", "DONNIE"}),
    frozenset({"RONALD", "RON", "RONNIE"}),
    frozenset({"KENNETH", "KEN", "KENNY"}),
    frozenset({"FRANCIS", "FRANK"}),
    frozenset({"FREDERICK", "FRED", "FREDDY"}),
    frozenset({"JEFFREY", "GEOFFREY", "JEFF"}),
    frozenset({"TERRENCE", "TERENCE", "TERRY"}),
    frozenset({"TIMOTHY", "TIM"}),
    frozenset({"PETER", "PETE"}),
    frozenset({"PHILIP", "PHILLIP", "PHIL"}),
    frozenset({"GREGORY", "GREG"}),
    frozenset({"JOSHUA", "JOSH"}),
    frozenset({"DEBORAH", "DEB", "DEBBIE"}),
    frozenset({"ELIZABETH", "LIZ", "BETH", "BETTY"}),
    frozenset({"KATHERINE", "KATHRYN", "KATE", "KATIE", "KATHY"}),
    frozenset({"CATHERINE", "CATHY", "KATE", "KATIE"}),
    frozenset({"MARGARET", "PEGGY", "MEG"}),
    frozenset({"SUSAN", "SUE", "SUSIE"}),
    frozenset({"JENNIFER", "JEN", "JENNY"}),
    frozenset({"BARBARA", "BARB"}),
)

_NON_CANDIDATES = {
    "OTHER",
    "UNDERVOTES",
    "UNDER VOTES",
    "OVERVOTES",
    "OVER VOTES",
    "VOID",
    "BLANK",
    "BLANK VOTES",
    "SCATTERING",
    "SCATTERED",
    "WRITE IN",
    "WRITEIN",
    "NONE OF THESE CANDIDATES",
    "NONE OF THE ABOVE",
}


def is_non_candidate(name: str | None) -> bool:
    """True for blank ballots, undervotes, and other non-person rows."""
    text = _letters(name)
    if not text:
        return True
    return text in _NON_CANDIDATES or text.startswith("NONE OF THESE")


def names_match(poll_name: str | None, result_name: str | None) -> bool:
    """True when a poll name and an official name are the same person string.

    Official returns sometimes invert the surname (``WYDEN RON``) or put the
    surname before a comma (``LAXALT, ADAM PAUL``). Given-name nicknames and
    a middle name used as the public name are accepted. Last names must match
    exactly after this cleanup.
    """
    poll = _forward_tokens(poll_name)
    if poll is None:
        return False
    return any(tokens_compatible(poll, orientation) for orientation in _orientations(result_name))


def tokens_compatible(poll: tuple[str, ...], result: tuple[str, ...]) -> bool:
    """Last names must match. Any given name may match, including a middle name.

    ``Doug Jones`` matches ``Gordon Douglas Jones``, and the reverse does too.
    Given names have to be the same token or a listed nickname. Last names are
    not fuzzy.
    """
    if len(poll) < 2 or len(result) < 2:
        return False
    if poll[-1] != result[-1]:
        return False
    return any(_nickname_equal(left, right) for left in poll[:-1] for right in result[:-1])


def _orientations(name: str | None) -> list[tuple[str, ...]]:
    prepared = _prepare(name)
    if not prepared:
        return []
    if "," in prepared:
        last_part, given_part = prepared.split(",", 1)
        tokens = _content_tokens(given_part) + _content_tokens(last_part)
        return [tuple(tokens)] if len(tokens) >= 2 else []
    tokens = _content_tokens(prepared)
    if len(tokens) < 2:
        return []
    forward = tuple(tokens)
    rotated = tuple(tokens[1:] + tokens[:1])
    if rotated == forward:
        return [forward]
    return [forward, rotated]


def _forward_tokens(name: str | None) -> tuple[str, ...] | None:
    prepared = _prepare(name)
    if not prepared or "," in prepared:
        tokens = _orientations(name)
        return tokens[0] if tokens else None
    tokens = _content_tokens(prepared)
    if len(tokens) < 2:
        return None
    return tuple(tokens)


def _content_tokens(text: str) -> list[str]:
    tokens = _tokenize(text)
    while tokens and tokens[0] in _TITLES:
        tokens.pop(0)
    while tokens and tokens[-1] in _SUFFIXES:
        tokens.pop()
    return [token for token in tokens if len(token) > 1 and token not in _TITLES]


def _prepare(name: str | None) -> str:
    if name is None:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.upper().replace("“", '"').replace("”", '"')
    text = re.sub(r'"[^"]*"', " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokenize(text: str) -> list[str]:
    cleaned = text.replace(".", " ")
    cleaned = re.sub(r"[^A-Z0-9'\s]", " ", cleaned)
    tokens = []
    for part in cleaned.split():
        part = part.strip("'")
        if part:
            tokens.append(part)
    return tokens


def _letters(name: str | None) -> str:
    prepared = _prepare(name)
    prepared = re.sub(r"[^A-Z0-9\s]", " ", prepared)
    return re.sub(r"\s+", " ", prepared).strip()


def _nickname_equal(left: str, right: str) -> bool:
    if left == right:
        return True
    return any(left in group and right in group for group in _NAME_GROUPS)
