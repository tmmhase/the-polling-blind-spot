"""Parser tests for 2026 Wikipedia Senate polling tables."""

from pathlib import Path

from polling_blind_spot.ingest.errors import DownloadError
from polling_blind_spot.ingest.wikipedia_2026 import (
    extract_poll_records,
    page_kind,
    state_from_title,
)

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "wikipedia_michigan_polling_excerpt.html"
)


def _records():
    return extract_poll_records(FIXTURE.read_text(encoding="utf-8"))


def test_state_titles_cover_regular_special_and_reject_the_overview():
    assert state_from_title("2026 United States Senate election in Alabama") == "Alabama"
    assert page_kind("2026 United States Senate election in Alabama") == "regular"
    assert (
        state_from_title("2026 United States Senate special election in Ohio") == "Ohio"
    )
    assert page_kind("2026 United States Senate special election in Ohio") == "special"
    for title in (
        "2026 United States Senate elections",
        "2026 United States Senate elections in Alabama",
    ):
        try:
            state_from_title(title)
        except DownloadError:
            continue
        raise AssertionError(f"{title} should not be treated as a state poll page")


def test_excerpt_keeps_polls_and_drops_results_and_infoboxes():
    records = _records()
    kinds = {row["table_kind"] for row in records}
    assert kinds == {"poll", "aggregation"}
    assert all(row["section_path"] == "General election > Polling" for row in records)
    assert all("Not a polling table" not in row["response_value"] for row in records)
    assert all(row["poll_source"] != "Should not be read" for row in records)


def test_aggregation_average_respects_colspan():
    records = [
        row
        for row in _records()
        if row["table_kind"] == "aggregation" and row["poll_source"] == "Average"
    ]
    by_label = {row["response_label"]: row["response_value"] for row in records}
    assert by_label == {
        "Abdul El-Sayed (D)": "48.4%",
        "Mike Rogers (R)": "44.9%",
        "Other/ Undecided": "6.7%",
        "Margin": "El-Sayed +3.5%",
    }
    assert all(row["dates_administered"] == "" for row in records)
    assert all(row["dates_updated"] == "" for row in records)
    assert all(row["metadata_inherited"] == "false" for row in records)


def test_rowspan_continuation_inherits_poll_metadata_and_strips_footnotes():
    records = [row for row in _records() if row["poll_source"] == "Quantus Insights (R)"]
    assert records
    assert all("[" not in row["poll_source"] for row in records)
    first = [row for row in records if row["row_index"] == "0"]
    second = [row for row in records if row["row_index"] == "1"]
    assert {row["response_value"] for row in first} == {"48%", "47%", "2%", "4%"}
    assert {row["response_value"] for row in second} == {"51%", "49%", "—"}
    assert all(row["metadata_inherited"] == "false" for row in first)
    assert all(row["metadata_inherited"] == "true" for row in second)
    assert all(row["dates_administered"] == "October 5–6, 2026" for row in second)
    assert all(row["sample_size"] == "762 (LV)" for row in second)
    assert all(row["margin_of_error"] == "± 3.9%" for row in second)


def test_collapsed_hypothetical_block_sets_the_table_group():
    html = """
    <h3 id="Polling">Polling</h3>
    <div class="hidden-title">Hypothetical polling</div>
    <table class="wikitable">
      <tr>
        <th>Poll source</th><th>Date(s) administered</th>
        <th>Sample size</th><th>Margin of error</th><th>Mark Warner (D)</th>
      </tr>
      <tr>
        <td>Virginia Commonwealth University</td>
        <td>December 18, 2024 – January 15, 2025</td>
        <td>806 (A)</td><td>± 4.7%</td><td>45%</td>
      </tr>
    </table>
    """
    records = extract_poll_records(html)
    assert len(records) == 1
    assert records[0]["table_group"] == "Hypothetical polling"
    assert records[0]["response_value"] == "45%"
    assert records[0]["poll_source"] == "Virginia Commonwealth University"


def test_pollster_link_is_preserved():
    yougov = [row for row in _records() if row["poll_source"] == "YouGov"]
    assert yougov
    assert all(
        row["poll_source_url"] == "https://en.wikipedia.org/wiki/YouGov" for row in yougov
    )
    assert {row["response_value"] for row in yougov} == {"49%", "48%", "1%", "2%"}
