import json
import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import DatabaseSession, bearer
from app.voice.schemas import VapiRequest
from app.voice.service import end_call, failure, process_tool

logger = logging.getLogger(__name__)


def require_vapi_secret(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = request.app.state.settings.vapi_webhook_secret.get_secret_value()
    if not expected:
        raise HTTPException(503, "Voice integration is not configured")
    if credentials is None or not secrets.compare_digest(
        credentials.credentials.encode(), expected.encode()
    ):
        raise HTTPException(401, "Invalid voice webhook credentials")


router = APIRouter(prefix="/vapi", tags=["voice"], dependencies=[Depends(require_vapi_secret)])


@router.post("/webhook")
def webhook(payload: VapiRequest, request: Request, session: DatabaseSession):
    message = payload.message
    expected = request.app.state.settings.vapi_assistant_id
    if expected and message.call.assistantId and message.call.assistantId != expected:
        raise HTTPException(403, "Unexpected assistant")
    if message.type == "tool-calls":
        try:
            calls = message.tools()
        except (ValueError, ValidationError, AttributeError) as exc:
            raise HTTPException(400, "Invalid tool-call envelope") from exc
        results = []
        for tool in calls:
            try:
                if len(calls) > 1 and tool.name == "confirm_registration":
                    result = failure(
                        "separate_confirmation_required",
                        "Confirmation must be a separate tool call "
                        "after the caller hears the readback.",
                    )
                else:
                    result = process_tool(session, message.call.id, tool)
            except SQLAlchemyError as exc:
                session.rollback()
                logger.error("voice_database_error exception=%s", type(exc).__name__)
                result = failure(
                    "database_error",
                    "I couldn't complete the save or lookup. "
                    "Please retry the same operation; do not claim success.",
                )
            except Exception as exc:
                session.rollback()
                logger.error("voice_internal_error exception=%s", type(exc).__name__)
                result = failure(
                    "internal_error", "The operation could not be verified. Do not claim success."
                )
            # Vapi requires this protocol shape, not the patient REST envelope.
            results.append({"toolCallId": tool.id, "result": json.dumps(result)})
        return {"results": results}
    if message.type == "end-of-call-report" or (
        message.type == "status-update" and message.status == "ended"
    ):
        end_call(session, message.call.id, message.endedReason, message.artifact.get("transcript"))
    return {"data": {"received": True}, "error": None}
