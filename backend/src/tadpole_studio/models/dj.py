from pydantic import BaseModel, Field
from typing import Optional


class DJConversationResponse(BaseModel):
    id: str
    title: str = "New Conversation"
    created_at: str = ""
    updated_at: str = ""


class DJMessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str  # "user", "assistant", "system"
    content: str
    generation_params_json: Optional[str] = None
    generation_job_id: Optional[str] = None
    created_at: str = ""


class DJConversationDetailResponse(DJConversationResponse):
    messages: list[DJMessageResponse] = Field(default_factory=list)


class CreateConversationRequest(BaseModel):
    title: str = "New Conversation"


class SendMessageRequest(BaseModel):
    content: str


class DJMessageResult(BaseModel):
    message: DJMessageResponse
    generation_job_id: Optional[str] = None
    fallback_notice: Optional[str] = None


class DJProviderInfo(BaseModel):
    name: str
    available: bool
    requires_api_key: bool
    models: list[str] = Field(default_factory=list)
    has_stored_api_key: bool = False
    has_api_base: bool = False
    api_base: Optional[str] = None
    package_installed: bool = True
    unavailable_reason: Optional[str] = None


class DJProvidersResponse(BaseModel):
    providers: list[DJProviderInfo] = Field(default_factory=list)
    active_provider: str = ""
    active_model: str = ""
    system_prompt: str = ""
    default_system_prompt: str = ""


class DJSettingsUpdate(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None


class RenameConversationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
