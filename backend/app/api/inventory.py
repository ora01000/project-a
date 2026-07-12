from fastapi import APIRouter, HTTPException, Request

from backend.app.services.inventory import get_inventory_service

router = APIRouter(tags=["inventory"])


@router.get("/inventory/status")
async def inventory_status(request: Request) -> dict:
    service = getattr(request.app.state, "inventory_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Inventory service is not initialized")
    return service.get_status_info()


@router.post("/inventory/reload")
async def reload_inventory(request: Request) -> dict:
    service = getattr(request.app.state, "inventory_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Inventory service is not initialized")

    loaded = service.reload_csv()
    return {
        "status": "ok",
        "loaded_rows": loaded,
        "document_count": service.document_count,
    }
