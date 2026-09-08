from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict:
    return {"ok": True, "service": "rentgraph-api", "version": "0.1.0"}
