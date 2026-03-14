from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from workspace_ai.workspace_api.models import BootstrapSetupRequest, ChatGPTImportRequest, CloneSessionRequest, ContextImportCreateRequest, ContextImportEnabledRequest, DebateCreateRequest, EventListResponse, ExecutionApprovalRequest, ExecutionCreateRequest, MessageCreateRequest, ResumeImportedSessionRequest, SessionCreateRequest, SessionStatusUpdateRequest, SettingsUpdateRequest
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

    @router.get("/context/preview")
    def context_preview(project_id: str = "workspace", import_ids: str = "") -> dict:
        ids = [i.strip() for i in import_ids.split(",") if i.strip()] if import_ids else None
        return manager.context_preview(project_id=project_id, context_import_ids=ids or None)

    @router.post("/context-imports")
    def create_context_import(request: ContextImportCreateRequest) -> dict:
        try:
            return manager.create_context_import(
                project_id=request.project_id,
                source_label=request.source_label,
                content=request.content,
                category=request.category,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/context-imports")
    def list_context_imports(project_id: str | None = None, limit: int = Query(default=200, ge=1, le=500)) -> dict:
        return manager.list_context_imports(project_id=project_id, limit=limit)

    @router.post("/context-imports/{import_id}/enabled")
    def set_context_import_enabled(import_id: str, request: ContextImportEnabledRequest) -> dict:
        result = manager.set_context_import_enabled(import_id=import_id, enabled=request.enabled)
        if result.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=f"Import not found: {import_id}")
        return result

    @router.delete("/context-imports/{import_id}")
    def delete_context_import(import_id: str) -> dict:
        return manager.delete_context_import(import_id=import_id)

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

    @router.get("/debates")
    def list_debates(project_id: str | None = None, limit: int = Query(default=50, ge=1, le=500)) -> dict:
        return manager.list_debates(project_id=project_id, limit=limit)

    @router.post("/debates")
    def start_debate(request: DebateCreateRequest) -> dict:
        try:
            return manager.start_debate(
                project_id=request.project_id,
                topic=request.topic,
                bottlenecks=request.bottlenecks,
                files=[item.model_dump() if hasattr(item, "model_dump") else item for item in request.files],
                participants=[participant.model_dump() for participant in request.participants],
                max_rounds=request.max_rounds,
                judge_provider=request.judge_provider,
                debate_style=request.debate_style,
                context_import_ids=request.context_import_ids or None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/debates/{debate_id}")
    def get_debate(debate_id: str) -> dict:
        payload = manager.get_debate(debate_id=debate_id)
        if payload.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=f"Debate not found: {debate_id}")
        return payload

    @router.get("/executions")
    def list_executions(project_id: str | None = None, limit: int = Query(default=50, ge=1, le=500)) -> dict:
        return manager.list_executions(project_id=project_id, limit=limit)

    @router.post("/executions")
    def create_execution(request: ExecutionCreateRequest) -> dict:
        try:
            return manager.create_execution(
                project_id=request.project_id,
                debate_id=request.debate_id,
                plan=request.plan,
                execution_mode=request.execution_mode,
                context_import_ids=request.context_import_ids or None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/executions/{execution_id}")
    def get_execution(execution_id: str) -> dict:
        payload = manager.get_execution(execution_id=execution_id)
        if payload.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=f"Execution not found: {execution_id}")
        return payload

    @router.post("/executions/{execution_id}/approval")
    def approve_execution(execution_id: str, request: ExecutionApprovalRequest) -> dict:
        try:
            payload = manager.decide_execution(execution_id=execution_id, approved=request.approved, note=request.note)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if payload.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=f"Execution not found: {execution_id}")
        return payload

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

    @router.delete("/sessions/{session_id}")
    def delete_session(session_id: str) -> dict:
        return manager.delete_session(session_id=session_id)

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
