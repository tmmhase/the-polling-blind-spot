"""The dashboard API serves committed outputs and does not invent 2026 scores."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from polling_blind_spot.api.catalog import Catalog, histogram
from polling_blind_spot.api.app import app

ROOT = Path(__file__).resolve().parents[1]
CLIENT = TestClient(app)


def test_histogram_keeps_every_observation_and_the_right_edge():
    bins = histogram([0, 1.9, 2, 4, -5, 9], start=0, stop=4, step=2)
    assert bins["counts"] == [2, 2]
    assert bins["underflow"] == 1
    assert bins["overflow"] == 1
    assert sum(bins["counts"]) + bins["underflow"] + bins["overflow"] == bins["n"]


def test_catalog_partitions_methodologies_and_passes_state_means_through():
    catalog = Catalog(ROOT)
    payload = catalog.pollsters()
    grouped = sum(row["n_questions"] for row in payload["methodology"])
    assert grouped == len(catalog.questions) == 3212
    live = next(row for row in payload["methodology"] if row["methodology"] == "Live Phone")
    assert live["n_questions"] == 811
    mixed = next(row for row in payload["methodology"] if row["methodology"] == "Mixed methods")
    assert mixed["n_questions"] > 0
    arizona = next(row for row in catalog.map_payload()["states"] if row["state_po"] == "AZ")
    assert arizona["n_questions"] == 371
    assert arizona["mean_signed_error"] == pytest.approx(3.2336)
    assert len(catalog.map_payload()["states"]) == 50


def test_error_and_simulation_histograms_cover_the_source_rows():
    catalog = Catalog(ROOT)
    errors = catalog.errors()["histogram"]
    assert errors["n"] == 3212
    assert sum(errors["counts"]) + errors["underflow"] + errors["overflow"] == 3212
    uncertainty = catalog.uncertainty()
    assert "observed poll" in uncertainty["simulation_note"]
    for design in uncertainty["designs"]:
        histogram_body = design["histogram"]
        assert design["n_draws"] == 2000
        assert histogram_body["n"] == 2000
        assert (
            sum(histogram_body["counts"]) + histogram_body["underflow"] + histogram_body["overflow"]
            == 2000
        )


def test_api_reads_committed_summaries():
    health = CLIENT.get("/api/health")
    assert health.status_code == 200
    assert health.json()["scored_questions"] == 3212

    overview = CLIENT.get("/api/overview").json()
    assert overview["poll_level"]["mean_signed_error"] == pytest.approx(3.6501)
    assert overview["race_level_unweighted_mean"]["mae"] == pytest.approx(5.3034)
    assert overview["model"]["seed"] == 20261018
    assert overview["model"]["sd_race_p50"] == pytest.approx(4.4776)

    polling_map = CLIENT.get("/api/map").json()
    assert "2026" in polling_map["score_note"]
    missing = {row["state_po"] for row in polling_map["states"] if not row["has_scored_questions"]}
    assert missing == {"CA", "HI", "LA"}
    california = next(row for row in polling_map["states"] if row["state_po"] == "CA")
    reasons = {item["reason"] for item in california["exclusions"]}
    assert "ambiguous_duplicate_ballot" in reasons

    hawaii = CLIENT.get("/api/states/HI")
    assert hawaii.status_code == 200
    assert hawaii.json()["questions"] == []
    assert hawaii.json()["has_scored_questions"] is False

    unknown = CLIENT.get("/api/states/ZZ")
    assert unknown.status_code == 404

    detail = CLIENT.get("/api/states/VT").json()
    assert detail["summary"]["n_questions"] == 3
    assert detail["summary"]["mean_signed_error"] == pytest.approx(-16.1073)
    assert detail["questions"]
    assert "2026" in detail["result_role"]

    firms = CLIENT.get("/api/pollsters", params={"min_questions": 187}).json()
    assert firms["pollsters"][0]["pollster"] == "Emerson"
    assert firms["pollsters"][0]["n_questions"] == 187

    notes = CLIENT.get("/api/notes").json()
    assert notes["sources"][0]["license"].startswith("Creative Commons")
    assert notes["limitations"]
    write_routes = [
        route
        for route in app.routes
        if getattr(route, "methods", None) and route.methods - {"GET", "HEAD"}
    ]
    assert write_routes == []
