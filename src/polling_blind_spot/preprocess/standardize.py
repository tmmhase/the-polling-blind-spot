"""Field parsers for Senate polls.

Each parser returns a missing value when the source did not publish a usable
figure. Bounds such as ``>1,000`` and ``<1%``, qualified shares such as
``5% U``, and month-only dates are not turned into point values.
"""

from __future__ import annotations

import re
from datetime import date
from typing import NamedTuple

STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}
NAME_BY_FOLD = {name.casefold(): name for name in STATE_NAMES.values()}

# Party codes that a source actually prints. DFL stays DFL here; the margin
# step treats it as the Democratic side because that is the Minnesota party label.
PARTY_CODES = {
    "D": "DEM",
    "DEM": "DEM",
    "R": "REP",
    "REP": "REP",
    "I": "IND",
    "IND": "IND",
    "L": "LIB",
    "LIB": "LIB",
    "G": "GRE",
    "GRE": "GRE",
    "DFL": "DFL",
    "PSL": "PSL",
}
DEMOCRATIC_PARTIES = {"DEM", "DFL"}
REPUBLICAN_PARTIES = {"REP"}

POPULATION_CODES = {
    "lv": "lv",
    "likely voters": "lv",
    "likely voter": "lv",
    "rv": "rv",
    "registered voters": "rv",
    "registered voter": "rv",
    "v": "v",
    "voters": "v",
    "voter": "v",
    "a": "a",
    "adults": "a",
    "adult": "a",
}

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_DASHES = re.compile(r"[–—−]")
_WS = re.compile(r"\s+")
_PAREN = re.compile(r"\(([^)]*)\)")
_PARTY_SUFFIX = re.compile(r"^(?P<name>.*?)\s*\((?P<code>[A-Za-z]{1,5})\)\s*$")
_FTE_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$")
_APPROX_DATE = re.compile(
    r"^(?:early|mid|late)\s*-?\s*(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})$",
    re.IGNORECASE,
)
_CROSS_YEAR = re.compile(
    r"^(?P<m1>[A-Za-z]+)\s+(?P<d1>\d{1,2}),\s*(?P<y1>\d{4})\s*-\s*"
    r"(?P<m2>[A-Za-z]+)\s+(?P<d2>\d{1,2}),\s*(?P<y2>\d{4})$",
    re.IGNORECASE,
)
_CROSS_MONTH = re.compile(
    r"^(?P<m1>[A-Za-z]+)\s+(?P<d1>\d{1,2})\s*-\s*"
    r"(?P<m2>[A-Za-z]+)\s+(?P<d2>\d{1,2}),\s*(?P<year>\d{4})$",
    re.IGNORECASE,
)
_SAME_MONTH = re.compile(
    r"^(?P<month>[A-Za-z]+)\s+(?P<start>\d{1,2})\s*-\s*(?P<end>\d{1,2}),\s*(?P<year>\d{4})$",
    re.IGNORECASE,
)
_ONE_DAY = re.compile(
    r"^(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})$",
    re.IGNORECASE,
)
_MONTH_ONLY = re.compile(r"^(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})$", re.IGNORECASE)
_AS_OF = re.compile(
    r"^through\s+(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})$",
    re.IGNORECASE,
)
_SAMPLE_NUMBER = re.compile(
    r"^(?P<prefix>[<>≈])?\s*(?P<number>\d{1,3}(?:,\d{3})+|\d+)(?:\.0+)?\s*"
    r"(?:\((?P<pop>[A-Za-z]{1,20})\))?$"
)
_SAMPLE_NO_NUMBER = re.compile(
    r"^(?:[-–—−]+|tba|n/?a)?\s*(?:\((?P<pop>[A-Za-z]{1,20})\))?$",
    re.IGNORECASE,
)
_PLAIN_PCT = re.compile(r"^(?P<number>\d{1,3}(?:\.\d+)?)\s*%$")
_CENSORED_PCT = re.compile(r"^[<>≈]\s*\d{1,3}(?:\.\d+)?\s*%$")
_QUALIFIED_PCT = re.compile(r"^\d{1,3}(?:\.\d+)?\s*%\s*[A-Za-z]{1,4}$")
_DASH_VALUE = re.compile(r"^(?:[-–—−]+(?:\s*n/?a)?|n/?a|not available)$", re.IGNORECASE)
_NOT_A_SHARE = re.compile(r"^\d{1,2}$|^[A-Z]{2,3}$")
_MOE = re.compile(r"^±\s*(?P<number>\d+(?:\.\d+)?)\s*%?$")
_PUBLISHED_MARGIN = re.compile(
    r"^(?P<leader>.+?)\s*\+\s*(?P<points>\d{1,3}(?:\.\d+)?)\s*%$"
)
_TIE = re.compile(r"^(?:tie|tied|even)$", re.IGNORECASE)
_FTE_STAGES = {
    "general": "general",
    "jungle primary": "jungle_primary",
    "runoff": "runoff",
}

_RESIDUAL = {"other", "someone else"}
_UNDECIDED = {"undecided", "undecided/not ranked", "not sure", "refused"}
_COMBINED_RESIDUAL = {"other/undecided"}
_MARGIN_LABELS = {"margin"}
_GENERICS = {
    "generic democrat": "DEM",
    "generic republican": "REP",
    "generic opponent": None,
}


class FieldDates(NamedTuple):
    start: date | None
    end: date | None
    grain: str


class ParsedSample(NamedTuple):
    sample_size: int | None
    population: str | None
    status: str


class ParsedShare(NamedTuple):
    pct: float | None
    status: str


class ParsedResponse(NamedTuple):
    role: str
    candidate_name: str | None
    party: str | None


class ParsedPollster(NamedTuple):
    name: str | None
    affiliation: str | None
    key: str | None


class PublishedMargin(NamedTuple):
    leader: str | None
    points: float | None
    tie: bool | None


def collapse(value: str | None) -> str:
    """Trim and collapse internal whitespace. Blank input stays blank."""
    if value is None:
        return ""
    return _WS.sub(" ", str(value)).strip()


def standardize_state(value: str | None) -> tuple[str | None, str | None]:
    """Return the canonical state name and postal code.

    An unrecognized place keeps its published text and gets no postal code.
    """
    text = collapse(value)
    if not text:
        return None, None
    if len(text) == 2 and text.upper() in STATE_NAMES:
        postal = text.upper()
        return STATE_NAMES[postal], postal
    canonical = NAME_BY_FOLD.get(text.casefold())
    if canonical is None:
        return text, None
    postal = next(code for code, name in STATE_NAMES.items() if name == canonical)
    return canonical, postal


def parse_fte_date(value: str | None) -> date | None:
    """Parse a FiveThirtyEight ``M/D/YY`` date. Blank stays missing."""
    text = collapse(value)
    if not text:
        return None
    match = _FTE_DATE.fullmatch(text)
    if match is None:
        return None
    month, day, year = (int(part) for part in match.groups())
    if year < 100:
        year += 2000 if year <= 49 else 1900
    return _safe_date(year, month, day)


def parse_field_dates(value: str | None) -> FieldDates:
    """Parse a Wikipedia fieldwork string without inventing a day.

    ``August 2025`` is month precision, so both endpoints stay missing.
    ``Mid-April 2025`` and ``Late June 2025`` are approximate and also have
    no endpoints. ``through October 10, 2026`` is an aggregator cutoff: the
    end date is kept and the start stays missing. A string that is not a
    date, such as a shifted percentage, is ``unparsed``.
    """
    original = collapse(value)
    if not original:
        return FieldDates(None, None, "missing")
    text = _DASHES.sub("-", original)
    approximate = _APPROX_DATE.fullmatch(text)
    if approximate and _month_number(approximate.group("month")) is not None:
        return FieldDates(None, None, "approximate")

    cross_year = _CROSS_YEAR.fullmatch(text)
    if cross_year:
        start = _safe_date(
            int(cross_year.group("y1")),
            _month_number(cross_year.group("m1")),
            int(cross_year.group("d1")),
        )
        end = _safe_date(
            int(cross_year.group("y2")),
            _month_number(cross_year.group("m2")),
            int(cross_year.group("d2")),
        )
        if start is not None and end is not None and start <= end:
            return FieldDates(start, end, "day")
        return FieldDates(None, None, "unparsed")

    cross_month = _CROSS_MONTH.fullmatch(text)
    if cross_month:
        year = int(cross_month.group("year"))
        start = _safe_date(year, _month_number(cross_month.group("m1")), int(cross_month.group("d1")))
        end = _safe_date(year, _month_number(cross_month.group("m2")), int(cross_month.group("d2")))
        if start is not None and end is not None and start <= end:
            return FieldDates(start, end, "day")
        return FieldDates(None, None, "unparsed")

    same_month = _SAME_MONTH.fullmatch(text)
    if same_month:
        year = int(same_month.group("year"))
        month = _month_number(same_month.group("month"))
        start = _safe_date(year, month, int(same_month.group("start")))
        end = _safe_date(year, month, int(same_month.group("end")))
        if start is not None and end is not None and start <= end:
            return FieldDates(start, end, "day")
        return FieldDates(None, None, "unparsed")

    one_day = _ONE_DAY.fullmatch(text)
    if one_day:
        parsed = _safe_date(
            int(one_day.group("year")),
            _month_number(one_day.group("month")),
            int(one_day.group("day")),
        )
        if parsed is None:
            return FieldDates(None, None, "unparsed")
        return FieldDates(parsed, parsed, "day")

    month_only = _MONTH_ONLY.fullmatch(text)
    if month_only and _month_number(month_only.group("month")) is not None:
        return FieldDates(None, None, "month")

    as_of = _AS_OF.fullmatch(text)
    if as_of:
        parsed = _safe_date(
            int(as_of.group("year")),
            _month_number(as_of.group("month")),
            int(as_of.group("day")),
        )
        if parsed is not None:
            return FieldDates(None, parsed, "as_of")
    return FieldDates(None, None, "unparsed")


def parse_population(value: str | None) -> str | None:
    """Map a published population label to ``lv``, ``rv``, ``v``, or ``a``."""
    text = collapse(value).casefold()
    if not text:
        return None
    return POPULATION_CODES.get(text)


def parse_numeric_sample(value: str | None) -> tuple[int | None, str]:
    """Parse a sample-size cell that is only a number, as in FiveThirtyEight."""
    text = collapse(value)
    if not text:
        return None, "missing"
    match = _SAMPLE_NUMBER.fullmatch(text)
    if match is None or match.group("pop") is not None or match.group("prefix"):
        return None, "unparsed"
    return int(match.group("number").replace(",", "")), "parsed"


def parse_wikipedia_sample(value: str | None) -> ParsedSample:
    """Parse ``1,200 (LV)``, ``— (LV)``, ``>1,000 (LV)``, and related cells."""
    text = collapse(value)
    if not text or _DASH_VALUE.fullmatch(text):
        return ParsedSample(None, None, "missing")
    numbered = _SAMPLE_NUMBER.fullmatch(text)
    if numbered:
        population = parse_population(numbered.group("pop"))
        if numbered.group("pop") and population is None:
            return ParsedSample(None, None, "unparsed")
        if numbered.group("prefix"):
            return ParsedSample(None, population, "censored")
        return ParsedSample(int(numbered.group("number").replace(",", "")), population, "parsed")
    empty = _SAMPLE_NO_NUMBER.fullmatch(text)
    if empty:
        population = parse_population(empty.group("pop"))
        if empty.group("pop") and population is None:
            return ParsedSample(None, None, "unparsed")
        return ParsedSample(None, population, "missing")
    return ParsedSample(None, None, "unparsed")


def parse_fte_pct(value: str | None) -> ParsedShare:
    """Parse a FiveThirtyEight percentage that is already a number."""
    text = collapse(value)
    if not text:
        return ParsedShare(None, "missing")
    try:
        number = float(text)
    except ValueError:
        return ParsedShare(None, "unparsed")
    if number < 0 or number > 100:
        return ParsedShare(None, "unparsed")
    return ParsedShare(round(number, 4), "parsed")


def parse_wikipedia_share(value: str | None) -> ParsedShare:
    """Parse one Wikipedia response cell.

    A plain percentage is kept. A dash is missing. ``<1%`` and ``5% U`` do
    not become point estimates. Bare round numbers and ``BA`` are ranked-choice
    markers, not vote shares.
    """
    text = collapse(value)
    if not text or _DASH_VALUE.fullmatch(text):
        return ParsedShare(None, "missing")
    plain = _PLAIN_PCT.fullmatch(text)
    if plain:
        number = float(plain.group("number"))
        if number > 100:
            return ParsedShare(None, "unparsed")
        return ParsedShare(round(number, 4), "parsed")
    if _CENSORED_PCT.fullmatch(text):
        return ParsedShare(None, "censored")
    if _QUALIFIED_PCT.fullmatch(text):
        return ParsedShare(None, "qualified")
    if _NOT_A_SHARE.fullmatch(text) or text.casefold() == "tba":
        return ParsedShare(None, "not_a_share")
    return ParsedShare(None, "unparsed")


def parse_margin_of_error(value: str | None) -> tuple[float | None, str]:
    """Parse a cell that was published with a plus-minus sign."""
    text = collapse(value)
    if not text or _DASH_VALUE.fullmatch(text):
        return None, "missing"
    match = _MOE.fullmatch(text)
    if match is None:
        return None, "unparsed"
    return round(float(match.group("number")), 4), "parsed"


def parse_published_margin(value: str | None) -> PublishedMargin:
    """Read a prose margin such as ``Rogers +3.5%`` without treating it as a share."""
    text = collapse(value)
    if not text or _DASH_VALUE.fullmatch(text):
        return PublishedMargin(None, None, None)
    if _TIE.fullmatch(text):
        return PublishedMargin(None, 0.0, True)
    match = _PUBLISHED_MARGIN.fullmatch(text)
    if match is None:
        return PublishedMargin(None, None, None)
    return PublishedMargin(collapse(match.group("leader")), round(float(match.group("points")), 4), False)


def classify_response_label(value: str | None) -> ParsedResponse:
    """Split a response header into a role, a name, and a party when printed."""
    text = collapse(value)
    if not text:
        return ParsedResponse("candidate", None, None)
    name, party = _split_party(text)
    key = _role_key(name)
    if key in _GENERICS:
        return ParsedResponse("generic", name, _GENERICS[key] or party)
    if key in _RESIDUAL:
        return ParsedResponse("residual", None, None)
    if key in _UNDECIDED:
        return ParsedResponse("undecided", None, None)
    if key in _COMBINED_RESIDUAL:
        return ParsedResponse("residual_undecided", None, None)
    if key in _MARGIN_LABELS:
        return ParsedResponse("published_margin", None, None)
    return ParsedResponse("candidate", name or None, party)


def standardize_pollster(value: str | None) -> ParsedPollster:
    """Normalize spacing and lift trailing party tags off a pollster name.

    ``Public Policy Polling (D)`` becomes the firm plus affiliation ``DEM``.
    ``co/efficient`` keeps its slash. A parenthetical that is not a party
    code, such as ``(Ohio)``, stays in the name.
    """
    text = collapse(value)
    if not text:
        return ParsedPollster(None, None, None)
    affiliations: list[str] = []

    def replace(match: re.Match[str]) -> str:
        code = PARTY_CODES.get(collapse(match.group(1)).upper())
        if code is None:
            return match.group(0)
        affiliations.append(code)
        return ""

    name = _PAREN.sub(replace, text)
    name = re.sub(r"\s*/\s*", "/", name)
    name = collapse(name).strip(" /")
    if not name:
        return ParsedPollster(None, "+".join(affiliations) or None, None)
    affiliation = "+".join(affiliations) or None
    return ParsedPollster(name, affiliation, name.casefold())


def pollster_is_implausible(value: str | None) -> bool:
    """True when a poll-source cell is a sample size, percentage, or blank.

    This catches Wikipedia rows whose columns were shifted. It does not guess
    the correct alignment.
    """
    text = collapse(value)
    if not text or "%" in text:
        return True
    without_tags = _PAREN.sub("", text)
    letters = re.sub(r"[^A-Za-z]", "", without_tags)
    return len(letters) < 2


def standardize_stage(value: str | None) -> str | None:
    """Map a FiveThirtyEight stage label onto the cleaned vocabulary."""
    text = collapse(value).casefold()
    if not text:
        return None
    return _FTE_STAGES.get(text)


def stage_from_section(section_path: str | None) -> str | None:
    """Map a Wikipedia polling heading to ``general``, ``primary``, or ``runoff``."""
    text = collapse(section_path).casefold()
    if not text:
        return None
    if "runoff" in text:
        return "runoff"
    if "primary" in text or "nominating" in text:
        return "primary"
    if "general" in text:
        return "general"
    return None


def section_is_ranked_choice(section_path: str | None) -> bool:
    text = collapse(section_path).casefold()
    return "ranked-choice" in text or "ranked choice" in text


def section_is_hypothetical(table_group: str | None, section_path: str | None) -> bool:
    blob = f"{collapse(table_group)} {collapse(section_path)}".casefold()
    return "hypothetical" in blob


def parse_flag(value: str | None) -> bool | None:
    """Parse true/false text. Blank stays missing rather than becoming false."""
    text = collapse(value).casefold()
    if text in {"true", "t", "yes"}:
        return True
    if text in {"false", "f", "no"}:
        return False
    return None


def isoformat(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _split_party(text: str) -> tuple[str, str | None]:
    match = _PARTY_SUFFIX.fullmatch(text)
    if match is None:
        return text, None
    code = PARTY_CODES.get(match.group("code").upper())
    if code is None:
        return text, None
    return collapse(match.group("name")), code


def _role_key(name: str) -> str:
    key = name.casefold()
    key = re.sub(r"\s*/\s*", "/", key)
    return collapse(key)


def _month_number(name: str | None) -> int | None:
    if name is None:
        return None
    return _MONTHS.get(name.casefold())


def _safe_date(year: int, month: int | None, day: int) -> date | None:
    if month is None:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None
