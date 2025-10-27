from fastapi import APIRouter, Request, HTTPException
from src.utils.logging.base_logger import setup_logger, modality_var

logger = setup_logger(__name__)
router = APIRouter()


@router.post("/ios")
async def handle_ios_webhook(request: Request):
    """Handles incoming iOS webhook updates."""
    modality_var.set("ios")

    try:
        data = await request.json()
    except Exception as e:
        logger.info(f"Invalid JSON in iOS webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    logger.info(f"Received data from iOS webhook: {data}")

    return {"status": "ok"}
