"""HTTP routes for the minimal FastAPI scaffold."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def get_health() -> dict[str, str]:
    """Return a minimal health response for local checks."""
    return {"status": "ok"}
