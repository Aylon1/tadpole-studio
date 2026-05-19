"""
AI DJ chat endpoints.

Inspired by:
- clockworksquirrel/ace-step-apple-silicon (conversational AI DJ interface)
"""

import asyncio
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException

from tadpole_studio.models.dj import (
    CreateConversationRequest,
    DJConversationDetailResponse,
    DJConversationResponse,
    DJMessageResponse,
    DJMessageResult,
    DJProvidersResponse,
    DJSettingsUpdate,
    RenameConversationRequest,
)
from tadpole_studio.services.dj_service import dj_service

router = APIRouter(prefix="/dj", tags=["dj"])


@router.get("/conversations", response_model=list[DJConversationResponse])
async def list_conversations() -> list[DJConversationResponse]:
    convs = await dj_service.list_conversations()
    return [DJConversationResponse(**c) for c in convs]


@router.post("/conversations", response_model=DJConversationResponse)
async def create_conversation(
    body: CreateConversationRequest,
) -> DJConversationResponse:
    conv = await dj_service.create_conversation(body.title)
    return DJConversationResponse(**conv)


@router.get(
    "/conversations/{conv_id}",
    response_model=DJConversationDetailResponse,
)
async def get_conversation(conv_id: str) -> DJConversationDetailResponse:
    conv = await dj_service.get_conversation(conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return DJConversationDetailResponse(
        id=conv["id"],
        title=conv["title"],
        created_at=conv["created_at"],
        updated_at=conv["updated_at"],
        messages=[DJMessageResponse(**m) for m in conv["messages"]],
    )


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str) -> dict:
    deleted = await dj_service.delete_conversation(conv_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True}


@router.post("/conversations/{conv_id}/messages", response_model=DJMessageResult)
async def send_message(
    conv_id: str,
    body: dict,
) -> DJMessageResult:
    content = body.get("content", "")
    if not content.strip():
        raise HTTPException(status_code=400, detail="Message content is required")

    result = await dj_service.send_message(conv_id, content)

    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])

    return DJMessageResult(
        message=DJMessageResponse(**result["message"]),
        generation_job_id=result.get("generation_job_id"),
        fallback_notice=result.get("fallback_notice"),
    )


@router.get("/providers", response_model=DJProvidersResponse)
async def get_providers() -> DJProvidersResponse:
    info = await dj_service.get_providers_info()
    return DJProvidersResponse(**info)


@router.patch("/conversations/{conv_id}")
async def rename_conversation(conv_id: str, body: RenameConversationRequest) -> dict:
    renamed = await dj_service.rename_conversation(conv_id, body.title)
    if not renamed:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"renamed": True}


@router.post("/install-cloud-packages")
async def install_cloud_packages() -> dict[str, str]:
    """Install openai + anthropic packages without re-resolving torch."""
    backend_dir = str(Path(__file__).resolve().parents[3])
    result = await asyncio.to_thread(
        subprocess.run,
        ["uv", "pip", "install", "openai>=1.0.0", "anthropic>=0.30.0"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=backend_dir,
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500, detail=result.stderr or "Install failed"
        )
    return {"message": "Packages installed successfully"}


@router.patch("/settings", response_model=DJProvidersResponse)
async def update_dj_settings(body: DJSettingsUpdate) -> DJProvidersResponse:
    info = await dj_service.update_settings(
        provider=body.provider,
        model=body.model,
        system_prompt=body.system_prompt,
        api_key=body.api_key,
        api_base=body.api_base,
    )
    return DJProvidersResponse(**info)
