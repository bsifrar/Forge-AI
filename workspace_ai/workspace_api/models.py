from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    project_id: str = Field(min_length=1)
    title: str = Field(default="")
    mode: str = Field(default="chat")


class DebateParticipantRequest(BaseModel):
    provider: str = Field(pattern="^(openai|xai|anthropic)$")
    model: str | None = Field(default=None)


class DebateArtifactRequest(BaseModel):
    path: str = Field(min_length=1)
    label: str = Field(default="")
    exists: bool = Field(default=True)
    kind: str = Field(default="text")
    size_bytes: int = Field(default=0, ge=0)
    preview: str = Field(default="", max_length=1200)


class DebateCreateRequest(BaseModel):
    project_id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    bottlenecks: str = Field(default="")
    files: List[str | DebateArtifactRequest] = Field(default_factory=list)
    participants: List[DebateParticipantRequest] = Field(default_factory=list)
    max_rounds: int = Field(default=5, ge=1, le=20)
    judge_provider: str | None = Field(default=None, pattern="^(openai|xai|anthropic)$")
    debate_style: str | None = Field(default=None, pattern="^(standard|fast|harsh_reviewer|side_by_side)$")


class ExecutionCreateRequest(BaseModel):
    project_id: str = Field(min_length=1)
    debate_id: str | None = Field(default=None)
    plan: str = Field(default="", max_length=12000)
    execution_mode: str = Field(default="read_only_v1", pattern="^(read_only_v1|change_plan_v1)$")


class ExecutionApprovalRequest(BaseModel):
    approved: bool
    note: str = Field(default="", max_length=4000)


class MessageCreateRequest(BaseModel):
    content: str = Field(min_length=1)
    role: str = Field(default="user")
    token_budget: int = Field(default=1800, ge=256, le=24000)
    model: str | None = Field(default=None)


class SettingsUpdateRequest(BaseModel):
    api_enabled: bool | None = Field(default=None)
    selected_provider: str | None = Field(default=None, pattern="^(openai|xai|anthropic)$")
    selected_model: str | None = Field(default=None)
    daily_spend_cap_usd: float | None = Field(default=None, ge=0.0)
    hourly_call_cap: int | None = Field(default=None, ge=0)
    price_input_per_1m_usd: float | None = Field(default=None, ge=0.0)
    price_output_per_1m_usd: float | None = Field(default=None, ge=0.0)
    api_key: str | None = Field(default=None)
    xai_api_key: str | None = Field(default=None)
    anthropic_api_key: str | None = Field(default=None)
    model_roles: Dict[str, Any] | None = Field(default=None)
    debate_style: str | None = Field(default=None, pattern="^(standard|fast|harsh_reviewer|side_by_side)$")
    personal_preferences: str | None = Field(default=None, max_length=4000)
    project_instructions: str | None = Field(default=None, max_length=4000)


class ChatGPTImportRequest(BaseModel):
    export_path: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    max_conversations: int = Field(default=25, ge=1, le=500)
    conversation_ids: List[str] = Field(default_factory=list)


class ResumeImportedSessionRequest(BaseModel):
    query: str = Field(min_length=1)
    project_id: str | None = Field(default=None)


class CloneSessionRequest(BaseModel):
    title: str | None = Field(default=None)
    include_messages: bool = Field(default=True)


class SessionStatusUpdateRequest(BaseModel):
    status: str = Field(pattern="^(active|archived)$")


class BootstrapSetupRequest(BaseModel):
    adapter_mode: str = Field(pattern="^(null|external)$")
    external_base_url: str | None = Field(default=None)
    api_enabled: bool = Field(default=True)
    selected_provider: str = Field(default="openai", pattern="^(openai|xai|anthropic)$")
    selected_model: str = Field(min_length=1)
    daily_spend_cap_usd: float = Field(default=20.0, ge=0.0)
    hourly_call_cap: int = Field(default=30, ge=0)
    price_input_per_1m_usd: float = Field(default=0.0, ge=0.0)
    price_output_per_1m_usd: float = Field(default=0.0, ge=0.0)
    api_key: str | None = Field(default=None)
    xai_api_key: str | None = Field(default=None)
    anthropic_api_key: str | None = Field(default=None)


class EventListResponse(BaseModel):
    session_id: str | None = Field(default=None)
    count: int
    events: List[Dict[str, Any]]
