from fastapi import APIRouter, Request, Response

router = APIRouter(tags=["demo"])


@router.get("/demo/config")
def demo_config(request: Request, response: Response):
    """Expose only the intentionally public browser SDK configuration."""
    settings = request.app.state.settings
    response.headers["Cache-Control"] = "no-store"
    return {
        "data": {
            "enabled": bool(settings.vapi_public_key and settings.vapi_assistant_id),
            "public_key": settings.vapi_public_key,
            "assistant_id": settings.vapi_assistant_id,
        },
        "error": None,
    }
