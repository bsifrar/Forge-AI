from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from workspace_ai.workspace_api.models import BootstrapSetupRequest, ChatGPTImportRequest, CloneSessionRequest, EventListResponse, MessageCreateRequest, ResumeImportedSessionRequest, SessionCreateRequest, SessionStatusUpdateRequest, SettingsUpdateRequest
from workspace_ai.workspace_api.streaming import encode_sse_stream
from workspace_ai.workspace_runtime.session_manager import SessionManager


def build_router(manager: SessionManager) -> APIRouter:
    router = APIRouter(prefix="/workspace", tags=["workspace"])

    @router.get("/status")
    def status() -> dict:
        return manager.status()

    @router.get("/adapter/status")
    def adapter_status() -> dict:
        return manager.adapter_status()

    @router.get("/settings")
    def settings() -> dict:
        return manager.settings()

    @router.post("/settings")
    def update_settings(request: SettingsUpdateRequest) -> dict:
        return manager.update_settings(request.model_dump())

    @router.post("/setup/bootstrap")
    def bootstrap_setup(request: BootstrapSetupRequest) -> dict:
        return manager.bootstrap_local_setup(request.model_dump())

    @router.post("/sessions")
    def create_session(request: SessionCreateRequest) -> dict:
        return manager.create_session(project_id=request.project_id, title=request.title, mode=request.mode)

    @router.get("/sessions")
    def list_sessions(project_id: str | None = None, limit: int = 50) -> dict:
        return manager.list_sessions(project_id=project_id, limit=limit)

    @router.get("/sessions/{session_id}")
    def get_session(session_id: str) -> dict:
        payload = manager.get_session(session_id)
        if payload is None:
            return {"status": "not_found", "session_id": session_id}
        return payload

    @router.get("/sessions/{session_id}/messages")
    def list_messages(session_id: str, limit: int = 200) -> dict:
        return manager.list_messages(session_id=session_id, limit=limit)

    @router.post("/sessions/{session_id}/clone")
    def clone_session(session_id: str, request: CloneSessionRequest) -> dict:
        return manager.clone_session(session_id=session_id, title=request.title, include_messages=request.include_messages)

    @router.post("/sessions/{session_id}/status")
    def update_session_status(session_id: str, request: SessionStatusUpdateRequest) -> dict:
        return manager.update_session_status(session_id=session_id, status=request.status)

    @router.get("/sessions/search")
    def search_sessions(q: str, project_id: str | None = None, limit: int = 25) -> dict:
        return manager.search_sessions(query=q, project_id=project_id, limit=limit)

    @router.post("/sessions/{session_id}/messages")
    def add_message(session_id: str, request: MessageCreateRequest) -> dict:
        return manager.add_message(session_id=session_id, content=request.content, role=request.role, token_budget=request.token_budget, model=request.model)

    @router.post("/sessions/{session_id}/messages/stream")
    def stream_message(session_id: str, request: MessageCreateRequest) -> StreamingResponse:
        stream = manager.stream_message(session_id=session_id, content=request.content, role=request.role, token_budget=request.token_budget, model=request.model)
        return StreamingResponse(encode_sse_stream(stream), media_type="text/event-stream")

    @router.get("/imports")
    def list_imports(project_id: str | None = None, limit: int = 50) -> dict:
        return manager.list_imports(project_id=project_id, limit=limit)

    @router.post("/imports/resume")
    def resume_import(request: ResumeImportedSessionRequest) -> dict:
        return manager.resume_imported_session(query=request.query, project_id=request.project_id)

    @router.post("/import/chatgpt-export")
    def import_chatgpt(request: ChatGPTImportRequest) -> dict:
        return manager.import_chatgpt_export(export_path=request.export_path, project_id=request.project_id, conversation_ids=request.conversation_ids, max_conversations=request.max_conversations)

    @router.post("/import/chatgpt-file")
    async def import_chatgpt_file(
        project_id: str = Form(...),
        max_conversations: int = Form(25),
        files: list[UploadFile] = File(...),
    ) -> dict:
        results = []
        imported_count = 0
        for file in files:
            payload = await file.read()
            result = manager.import_chatgpt_file(
                file_bytes=payload,
                filename=file.filename or "conversations.json",
                project_id=project_id,
                max_conversations=max_conversations,
            )
            results.append(result)
            imported_count += int(result.get("imported_count") or 0)
        status = "ok" if any(result.get("status") == "ok" for result in results) else "invalid"
        return {
            "status": status,
            "project_id": project_id,
            "file_count": len(files),
            "imported_count": imported_count,
            "results": results,
        }

    @router.get("/events", response_model=EventListResponse)
    def events(session_id: str | None = None, limit: int = 100) -> EventListResponse:
        return EventListResponse(**manager.stream_manager.list_events(session_id=session_id, limit=limit))

    return router
