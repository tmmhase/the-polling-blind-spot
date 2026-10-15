"""Download 2026 U.S. Senate polling tables from English Wikipedia.

State election articles are the public source. The national overview page is
not scraped: it repeats ratings and summaries rather than the state poll
tables. Each saved HTML page is the REST HTML for one revision, and the CSV
is a long extract of those tables. Aggregation rows stay in the file and are
labeled ``table_kind=aggregation`` so later analysis can drop them.

Rowspan cells are copied onto later rows and flagged ``metadata_inherited``.
Colspan on a data cell, such as the Average row spanning the date columns,
occupies those columns without copying the label into them. Footnotes inside
``sup`` are omitted. Empty cells are not filled in.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from polling_blind_spot.ingest.errors import DownloadError
from polling_blind_spot.ingest.http import download_bytes, download_html
from polling_blind_spot.ingest.schemas import (
    WIKIPEDIA_COLUMNS,
    validate_csv_bytes,
    validate_wikipedia_bundle,
)

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_REST_HTML = "https://en.wikipedia.org/api/rest_v1/page/html/{title}"
WIKIPEDIA_LICENSE = "CC BY-SA 4.0"
WIKIPEDIA_LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
WIKIPEDIA_TERMS_URL = "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use"

CSV_FILENAME = "wikipedia_2026_us_senate_polls.csv"
MANIFEST_FILENAME = "wikipedia_2026_us_senate_manifest.json"
HTML_DIRNAME = "wikipedia_2026_pages"

PAGE_PREFIXES = (
    "2026 United States Senate election",
    "2026 United States Senate special election",
)
OVERVIEW_TITLE = "2026 United States Senate elections"
STATE_TITLE = re.compile(
    r"^2026 United States Senate (?P<special>special )?election in (?P<state>.+)$"
)

REQUEST_PAUSE_SECONDS = 0.25
_WHITESPACE = re.compile(r"\s+")
_EDIT_SUFFIX = re.compile(r"\s*\[edit\]\s*$", re.IGNORECASE)
_FOOTNOTE_SUFFIX = re.compile(r"\s*\[[0-9a-z]{1,3}\]$")


@dataclass
class Cell:
    text: str
    href: str
    is_header: bool
    inherited: bool
    covered: bool


def download_wikipedia_2026(raw_dir: Path, *, force: bool = False) -> Path:
    """Fetch state-page HTML and write the long polling extract."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    csv_path = raw_dir / CSV_FILENAME
    manifest_path = raw_dir / MANIFEST_FILENAME
    if csv_path.exists() and manifest_path.exists() and not force:
        report = validate_wikipedia_bundle(csv_path, manifest_path, raw_dir)
        print(
            f"Using existing {csv_path} "
            f"({report['n_rows']} response cells, "
            f"{report['n_states_with_polls']} states with individual polls)"
        )
        return csv_path

    retrieved_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pages, redirects = discover_state_pages()
    if len(pages) < 30:
        raise DownloadError(
            f"Wikipedia listing returned only {len(pages)} state election pages; "
            "refusing to write a partial extract"
        )

    html_dir = raw_dir / HTML_DIRNAME
    html_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, str]] = []
    manifest_pages: list[dict] = []

    for index, page in enumerate(pages, start=1):
        title = page["title"]
        rest_url = _rest_url(title)
        print(f"[{index}/{len(pages)}] {title}")
        payload, headers = _download_html_with_retry(rest_url)
        revision_id = headers.get("content-revision-id", "").strip()
        if not revision_id.isdigit():
            raise DownloadError(f"Wikipedia did not return a revision id for {title}")
        html_name = f"{page['pageid']}.html"
        html_path = html_dir / html_name
        html_path.write_bytes(payload)
        extracted = extract_poll_records(payload.decode("utf-8", errors="replace"))
        kind = page_kind(title)
        state_name = state_from_title(title)
        canonical_url = page.get("fullurl") or _wiki_url(title)
        for record in extracted:
            records.append(
                {
                    "retrieved_at": retrieved_at,
                    "page_id": str(page["pageid"]),
                    "page_title": title,
                    "revision_id": revision_id,
                    "canonical_url": canonical_url,
                    "state_name": state_name,
                    "election_kind": kind,
                    **record,
                }
            )
        poll_cells = sum(1 for row in extracted if row["table_kind"] == "poll")
        aggregation_cells = sum(1 for row in extracted if row["table_kind"] == "aggregation")
        print(
            f"  revision {revision_id}: {poll_cells} poll cells, "
            f"{aggregation_cells} aggregation cells"
        )
        manifest_pages.append(
            {
                "title": title,
                "page_id": page["pageid"],
                "revision_id": int(revision_id),
                "api_last_revision_id": page.get("lastrevid"),
                "canonical_url": canonical_url,
                "rest_url": rest_url,
                "html_path": f"{HTML_DIRNAME}/{html_name}",
                "html_bytes": len(payload),
                "html_sha256": hashlib.sha256(payload).hexdigest(),
                "n_poll_response_rows": poll_cells,
                "n_aggregation_response_rows": aggregation_cells,
                "state_name": state_name,
                "election_kind": kind,
            }
        )
        time.sleep(REQUEST_PAUSE_SECONDS)

    _write_csv(csv_path, records)
    stats = validate_csv_bytes(csv_path.read_bytes(), CSV_FILENAME)
    manifest = {
        "source": "English Wikipedia, via the MediaWiki REST HTML endpoint",
        "retrieved_at": retrieved_at,
        "license": WIKIPEDIA_LICENSE,
        "license_url": WIKIPEDIA_LICENSE_URL,
        "terms_url": WIKIPEDIA_TERMS_URL,
        "api_url": WIKIPEDIA_API_URL,
        "rest_html_template": WIKIPEDIA_REST_HTML,
        "attribution": (
            "Polling tables are from the English Wikipedia articles named in "
            "pages, at the revision_id stored for each page. Text is available "
            "under CC BY-SA 4.0."
        ),
        "excluded_titles": [
            {
                "title": OVERVIEW_TITLE,
                "reason": (
                    "National overview of race ratings and summaries. "
                    "State and special-election articles are the polling source."
                ),
            }
        ],
        "redirects": redirects,
        "csv_path": CSV_FILENAME,
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "csv_rows": stats["n_rows"],
        "pages": manifest_pages,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    report = validate_wikipedia_bundle(csv_path, manifest_path, raw_dir)
    print(
        f"Wrote {csv_path} ({report['n_rows']} response cells, "
        f"{report['poll_response_rows']} from individual polls, "
        f"{report['n_states_with_polls']} states)"
    )
    return csv_path


def discover_state_pages() -> tuple[list[dict], list[dict[str, str]]]:
    """List canonical 2026 Senate state articles, following redirects once."""
    titles: list[str] = []
    for prefix in PAGE_PREFIXES:
        titles.extend(page["title"] for page in _allpages(prefix))
    unique_titles = list(dict.fromkeys(titles))
    pages_by_id, redirects = _resolve_titles(unique_titles)
    selected = []
    for page in pages_by_id.values():
        title = page.get("title", "")
        if STATE_TITLE.match(title):
            selected.append(page)
    selected.sort(key=lambda page: (state_from_title(page["title"]), page["title"]))
    return selected, redirects


def state_from_title(title: str) -> str:
    match = STATE_TITLE.match(title)
    if not match:
        raise DownloadError(f"Not a 2026 Senate state page title: {title}")
    return match.group("state").strip()


def page_kind(title: str) -> str:
    match = STATE_TITLE.match(title)
    if not match:
        raise DownloadError(f"Not a 2026 Senate state page title: {title}")
    return "special" if match.group("special") else "regular"


def extract_poll_records(html: str) -> list[dict[str, str]]:
    """Return long-form poll and aggregation cells from one article's HTML."""
    records: list[dict[str, str]] = []
    stack: list[tuple[int, str, str]] = []
    in_polling = False
    section_path = ""
    section_anchor = ""
    table_counts: dict[str, int] = {}
    active_group = ""

    for event in _HtmlEvents(html).events():
        kind = event[0]
        if kind == "group":
            if in_polling:
                active_group = event[1]
            continue
        if kind == "heading":
            active_group = ""
            _, level, text, anchor = event
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, text, anchor))
            in_polling = any(_is_polling_heading(item[1]) for item in stack)
            if in_polling:
                section_path = " > ".join(item[1] for item in stack)
                section_anchor = _polling_anchor(stack)
            continue
        if kind != "table" or not in_polling:
            continue
        table_records = _records_from_table(event[1])
        if not table_records:
            continue
        table_index = table_counts.get(section_anchor, 0)
        table_counts[section_anchor] = table_index + 1
        for record in table_records:
            record["section_anchor"] = section_anchor
            record["section_path"] = section_path
            record["table_index"] = str(table_index)
            if not record["table_group"]:
                record["table_group"] = active_group
            records.append(record)
    return records


def _records_from_table(rows: list[list[Cell]]) -> list[dict[str, str]]:
    header_buf: list[list[Cell]] = []
    headers: list[str] | None = None
    table_kind: str | None = None
    table_group = ""
    data_index = 0
    records: list[dict[str, str]] = []

    def flush_headers() -> None:
        nonlocal headers, table_kind
        if not header_buf:
            return
        headers = _merge_headers(header_buf)
        header_buf.clear()
        if table_kind is None:
            table_kind = _classify_table(headers)

    for row in rows:
        if _is_group_row(row):
            flush_headers()
            table_group = next(cell.text for cell in row if cell.text.strip() and not cell.covered)
            continue
        if _is_column_header_row(row):
            header_buf.append(row)
            continue
        flush_headers()
        if table_kind is None or not headers:
            return []
        emitted = _response_records(headers, row, table_kind, table_group, data_index)
        if emitted:
            records.extend(emitted)
            data_index += 1
    return records if table_kind in {"poll", "aggregation"} else []


def _response_records(
    headers: list[str],
    row: list[Cell],
    table_kind: str,
    table_group: str,
    row_index: int,
) -> list[dict[str, str]]:
    fields = {
        "poll_source": "",
        "poll_source_url": "",
        "dates_administered": "",
        "dates_updated": "",
        "sample_size": "",
        "margin_of_error": "",
    }
    inherited = False
    responses: list[tuple[int, str, str]] = []
    width = min(len(headers), len(row))
    for index in range(width):
        label = headers[index]
        cell = row[index]
        if not label:
            continue
        role = _header_role(label)
        if role == "response":
            if cell.covered:
                continue
            value = _clean_value(cell.text)
            if not value:
                continue
            responses.append((index, label, value))
            continue
        if cell.inherited:
            inherited = True
        if cell.covered or not cell.text.strip():
            continue
        if not fields[role]:
            fields[role] = _clean_text(cell.text)
            if role == "poll_source":
                fields["poll_source_url"] = cell.href
    if not responses:
        return []
    inherited_flag = "true" if inherited else "false"
    return [
        {
            "table_kind": table_kind,
            "table_group": table_group,
            "row_index": str(row_index),
            "metadata_inherited": inherited_flag,
            "poll_source": fields["poll_source"],
            "poll_source_url": fields["poll_source_url"],
            "dates_administered": fields["dates_administered"],
            "dates_updated": fields["dates_updated"],
            "sample_size": fields["sample_size"],
            "margin_of_error": fields["margin_of_error"],
            "response_column_index": str(column_index),
            "response_label": label,
            "response_value": value,
        }
        for column_index, label, value in responses
    ]


def _classify_table(headers: list[str]) -> str | None:
    norms = [_normalize(header) for header in headers if header]
    if any("aggregation" in header for header in norms):
        return "aggregation"
    roles = {_header_role(header) for header in headers if header}
    if "poll_source" in roles and "dates_administered" in roles:
        return "poll"
    return None


def _header_role(label: str) -> str:
    header = _normalize(label)
    if "aggregation" in header and "source" in header:
        return "poll_source"
    if header in {"poll source", "pollster", "poll"} or header.startswith("poll source"):
        return "poll_source"
    if header.startswith("pollster"):
        return "poll_source"
    if "margin of error" in header or header in {"moe", "m.o.e."}:
        return "margin_of_error"
    if "sample" in header:
        return "sample_size"
    if "date" in header and "update" in header:
        return "dates_updated"
    if "date" in header:
        return "dates_administered"
    return "response"


def _is_column_header_row(row: list[Cell]) -> bool:
    cells = [cell for cell in row if cell.text.strip()]
    if len(cells) < 3 or not all(cell.is_header for cell in cells):
        return False
    norms = [_normalize(cell.text) for cell in cells]
    return any(any(token in norm for token in ("poll", "date", "sample", "margin")) for norm in norms)


def _is_group_row(row: list[Cell]) -> bool:
    origins = [cell for cell in row if cell.text.strip() and not cell.covered]
    if len(origins) != 1:
        return False
    cell = origins[0]
    norm = _normalize(cell.text)
    if "poll source" in norm or norm in {"pollster", "date", "dates"}:
        return False
    if _PERCENTISH.match(cell.text.strip()):
        return False
    return cell.is_header or any(other.covered for other in row)


_PERCENTISH = re.compile(r"^[<>≈]?\s*\d{1,3}(?:\.\d+)?\s*%$")


def _merge_headers(rows: list[list[Cell]]) -> list[str]:
    width = max(len(row) for row in rows)
    labels: list[str] = []
    for index in range(width):
        parts: list[str] = []
        for row in rows:
            if index >= len(row):
                continue
            text = _clean_text(row[index].text)
            if text and text not in parts:
                parts.append(text)
        labels.append(" / ".join(parts))
    return labels


def _is_polling_heading(text: str) -> bool:
    norm = _normalize(text)
    return norm == "polling" or norm.startswith("polling ")


def _polling_anchor(stack: list[tuple[int, str, str]]) -> str:
    for _, text, anchor in reversed(stack):
        if _is_polling_heading(text):
            return anchor or _normalize(text).replace(" ", "-")
    return ""


def _allpages(prefix: str) -> list[dict]:
    pages: list[dict] = []
    token = None
    while True:
        params = {
            "action": "query",
            "list": "allpages",
            "apprefix": prefix,
            "apnamespace": "0",
            "aplimit": "50",
        }
        if token:
            params["apcontinue"] = token
        payload = _mediawiki(params)
        pages.extend(payload["query"]["allpages"])
        token = payload.get("continue", {}).get("apcontinue")
        if not token:
            return pages


def _resolve_titles(titles: list[str]) -> tuple[dict[int, dict], list[dict[str, str]]]:
    pages: dict[int, dict] = {}
    redirects: list[dict[str, str]] = []
    for start in range(0, len(titles), 40):
        batch = titles[start : start + 40]
        payload = _mediawiki(
            {
                "action": "query",
                "titles": "|".join(batch),
                "redirects": "1",
                "prop": "info",
                "inprop": "url",
            }
        )
        for item in payload.get("query", {}).get("redirects", []):
            redirects.append({"from": item.get("from", ""), "to": item.get("to", "")})
        for page in payload.get("query", {}).get("pages", {}).values():
            if "missing" in page or "pageid" not in page:
                continue
            pages[int(page["pageid"])] = page
        time.sleep(REQUEST_PAUSE_SECONDS)
    return pages, redirects


def _mediawiki(params: dict) -> dict:
    last_error: DownloadError | None = None
    for attempt in range(4):
        query = urllib.parse.urlencode({**params, "format": "json", "maxlag": "5"})
        url = f"{WIKIPEDIA_API_URL}?{query}"
        try:
            payload = download_bytes(url, timeout=90)
            body = json.loads(payload.decode("utf-8"))
        except (DownloadError, json.JSONDecodeError) as exc:
            last_error = exc if isinstance(exc, DownloadError) else DownloadError(str(exc))
            time.sleep(2 ** attempt)
            continue
        error = body.get("error")
        if error:
            code = error.get("code", "")
            if code in {"maxlag", "ratelimited"} and attempt < 3:
                time.sleep(5)
                continue
            raise DownloadError(f"Wikipedia API error {code}: {error.get('info', '')}")
        return body
    raise last_error or DownloadError("Wikipedia API request failed")


def _download_html_with_retry(url: str) -> tuple[bytes, dict[str, str]]:
    last_error: DownloadError | None = None
    for attempt in range(4):
        try:
            return download_html(url, timeout=120)
        except DownloadError as exc:
            last_error = exc
            time.sleep(2 ** attempt)
    raise last_error or DownloadError(f"Failed to download {url}")


def _write_csv(path: Path, records: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=WIKIPEDIA_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow({column: record.get(column, "") for column in WIKIPEDIA_COLUMNS})


def _rest_url(title: str) -> str:
    slug = urllib.parse.quote(title.replace(" ", "_"), safe="()'!$*,-._:")
    return WIKIPEDIA_REST_HTML.format(title=slug)


def _wiki_url(title: str) -> str:
    slug = urllib.parse.quote(title.replace(" ", "_"), safe="()'!$*,-._:")
    return f"https://en.wikipedia.org/wiki/{slug}"


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text.replace("\xa0", " ")).strip().lower()


def _clean_text(text: str) -> str:
    cleaned = _EDIT_SUFFIX.sub("", text.replace("\xa0", " "))
    return _WHITESPACE.sub(" ", cleaned).strip()


def _clean_value(text: str) -> str:
    return _FOOTNOTE_SUFFIX.sub("", _clean_text(text)).strip()


class _HtmlEvents(HTMLParser):
    """Stream headings and wikitable grids from a Wikipedia HTML page."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self._html = html
        self._events: list[tuple] = []
        self._table_depth = 0
        self._active_table = False
        self._rows: list[list[Cell]] = []
        self._pending: dict[tuple[int, int], Cell] = {}
        self._raw_row: list[dict] | None = None
        self._cell: dict | None = None
        self._ignore: list[str] = []
        self._heading_level: int | None = None
        self._heading_anchor = ""
        self._heading_parts: list[str] = []
        self._capture_group = False
        self._group_parts: list[str] = []

    def events(self) -> list[tuple]:
        self.feed(self._html)
        self.close()
        return self._events

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "sup"}:
            self._ignore.append(tag)
            return
        if self._ignore:
            return
        attributes = {key: value or "" for key, value in attrs}
        if tag == "div" and self._table_depth == 0 and "hidden-title" in attributes.get("class", "").split():
            self._capture_group = True
            self._group_parts = []
        if tag in {"h2", "h3", "h4"} and self._table_depth == 0:
            self._heading_level = int(tag[1])
            self._heading_anchor = attributes.get("id", "")
            self._heading_parts = []
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1 and "wikitable" in attributes.get("class", "").split():
                self._active_table = True
                self._rows = []
                self._pending = {}
            return
        if not self._active_table or self._table_depth != 1:
            return
        if tag == "tr":
            self._raw_row = []
            return
        if tag in {"td", "th"} and self._raw_row is not None:
            self._cell = {
                "tag": tag,
                "text": [],
                "href": "",
                "colspan": _span(attributes.get("colspan", "")),
                "rowspan": _span(attributes.get("rowspan", "")),
            }
            return
        if tag == "br" and self._cell is not None:
            self._cell["text"].append(" ")
            return
        if tag == "a" and self._cell is not None and not self._cell["href"]:
            href = attributes.get("href", "")
            if href and not href.startswith("#"):
                self._cell["href"] = _absolute_href(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "sup"} and self._ignore and self._ignore[-1] == tag:
            self._ignore.pop()
            return
        if self._ignore:
            return
        if tag == "div" and self._capture_group:
            text = _clean_text("".join(self._group_parts))
            if text:
                self._events.append(("group", text))
            self._capture_group = False
            self._group_parts = []
            return
        if tag in {"h2", "h3", "h4"} and self._heading_level == int(tag[1]):
            text = _clean_text("".join(self._heading_parts))
            if text:
                self._events.append(("heading", self._heading_level, text, self._heading_anchor))
            self._heading_level = None
            return
        if tag in {"td", "th"} and self._cell is not None:
            self._raw_row.append(self._cell)
            self._cell = None
            return
        if tag == "tr" and self._raw_row is not None and self._active_table:
            self._rows.append(_expand_row(len(self._rows), self._raw_row, self._pending))
            self._raw_row = None
            return
        if tag == "table" and self._table_depth:
            if self._table_depth == 1 and self._active_table:
                self._events.append(("table", self._rows))
                self._active_table = False
                self._rows = []
                self._pending = {}
            self._table_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignore:
            return
        if self._capture_group:
            self._group_parts.append(data)
        if self._heading_level is not None and self._table_depth == 0:
            self._heading_parts.append(data)
        if self._cell is not None:
            self._cell["text"].append(data)


def _expand_row(
    row_index: int,
    raw_cells: list[dict],
    pending: dict[tuple[int, int], Cell],
) -> list[Cell]:
    """Place raw cells around rowspan cells carried down from earlier rows.

    A header colspan copies its label across the spanned columns. A data
    colspan keeps the text in the first column and marks the rest covered,
    which is how Wikipedia's Average row spans source and date columns.
    Rowspan copies the visible text onto later rows and marks it inherited.
    """
    output: list[Cell] = []
    column = 0

    def take_pending() -> None:
        nonlocal column
        while (row_index, column) in pending:
            output.append(pending.pop((row_index, column)))
            column += 1

    for raw in raw_cells:
        take_pending()
        text = _clean_text("".join(raw["text"]))
        href = raw["href"]
        is_header = raw["tag"] == "th"
        colspan = raw["colspan"]
        rowspan = raw["rowspan"]
        for offset in range(colspan):
            if is_header:
                cell = Cell(text, href if offset == 0 else "", True, False, offset > 0)
                carried = Cell(text, href if offset == 0 else "", True, True, offset > 0)
            else:
                cell = Cell(
                    text if offset == 0 else "",
                    href if offset == 0 else "",
                    False,
                    False,
                    offset > 0,
                )
                carried = Cell(
                    text if offset == 0 else "",
                    href if offset == 0 else "",
                    False,
                    True,
                    offset > 0,
                )
            output.append(cell)
            for depth in range(1, rowspan):
                pending[(row_index + depth, column + offset)] = carried
        column += colspan
    take_pending()
    return output


def _span(value: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 1
    return parsed if parsed > 0 else 1


def _absolute_href(href: str) -> str:
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return "https://en.wikipedia.org" + href
    return href
