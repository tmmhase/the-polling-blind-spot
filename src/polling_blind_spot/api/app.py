"""FastAPI service for the polling-error dashboard.

The routes are read-only. They serve tables already written under ``outputs/``.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from polling_blind_spot.api.catalog import CatalogError, get_catalog

app = FastAPI(
    title="The Polling Blind Spot",
    version="0.1.0",
    summary="Historical Senate polling error and uncertainty outputs.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.exception_handler(CatalogError)
def missing_output(_request, exc: CatalogError):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/api/health")
def health() -> dict[str, object]:
    catalog = get_catalog()
    return {
        "status": "ok",
        "scored_questions": len(catalog.questions),
        "races": len(catalog.race_rows),
    }


@app.get("/api/overview")
def overview() -> dict[str, object]:
    return get_catalog().overview()


@app.get("/api/map")
def polling_map() -> dict[str, object]:
    return get_catalog().map_payload()


@app.get("/api/states/{state_po}")
def state_detail(state_po: str) -> dict[str, object]:
    catalog = get_catalog()
    if state_po.upper() not in catalog._states:
        raise HTTPException(status_code=404, detail=f"Unknown state code: {state_po}")
    return catalog.state_detail(state_po)


@app.get("/api/errors")
def errors() -> dict[str, object]:
    return get_catalog().errors()


@app.get("/api/pollsters")
def pollsters(min_questions: int = Query(default=1, ge=1)) -> dict[str, object]:
    return get_catalog().pollsters(min_questions=min_questions)


@app.get("/api/uncertainty")
def uncertainty() -> dict[str, object]:
    return get_catalog().uncertainty()


@app.get("/api/notes")
def notes() -> dict[str, object]:
    return get_catalog().notes()
