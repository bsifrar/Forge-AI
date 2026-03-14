from __future__ import annotations

import json
from typing import Any, Dict, List

from workspace_ai.providers import get_provider
from workspace_ai.workspace_runtime.artifact_service import ArtifactService
from workspace_ai.workspace_memory.session_store import SessionStore
from workspace_ai.workspace_runtime.chat_service import ChatService
from workspace_ai.workspace_runtime.settings_service import SettingsService


_VALID_STYLES = {"standard", "fast", "harsh_reviewer", "side_by_side"}

_STYLE_CONFIGS: Dict[str, str] = {
    "standard": "",
    "fast": (
        "Be concise. Aim for rapid convergence. Skip lengthy preambles and reach a "
        "working recommendation quickly. Prefer agreement over exhaustive analysis."
    ),
    "harsh_reviewer": (
        "Be a rigorous critic. Challenge every assumption and expose weaknesses before "
        "proposing improvements. Do not soften your critique."
    ),
    "side_by_side": (
        "Present your own position completely and independently. Do not react to or "
        "acknowledge other positions — state your case on its own merits."
    ),
}


class DebateService:
    def __init__(self, *, store: SessionStore, settings_service: SettingsService, max_rounds: int = 5) -> None:
        self.store = store
        self.settings_service = settings_service
        self.max_rounds = max(1, int(max_rounds))
        self.artifact_service = ArtifactService()

    @staticmethod
    def _normalize_provider(value: str | None, *, field_name: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"openai", "xai", "anthropic"}:
            raise ValueError(f"{field_name} must be one of: openai, xai, anthropic")
        return normalized

    def _normalize_participants(self, participants: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
        if not participants:
            role_a = self.settings_service.model_role("debate_a")
            role_b = self.settings_service.model_role("debate_b")
            return [
                {"provider": role_a["provider"], "model": role_a["model"]},
                {"provider": role_b["provider"], "model": role_b["model"]},
            ]
        normalized: List[Dict[str, Any]] = []
        for item in participants:
            provider_name = self._normalize_provider(str(item.get("provider") or ""), field_name="participants.provider")
            selected_model = str(item.get("model") or "").strip()
            normalized.append({"provider": provider_name, "model": selected_model or None})
        if not normalized:
            raise ValueError("participants must include at least one provider")
        return normalized

    def start_debate(
        self,
        *,
        project_id: str,
        topic: str,
        bottlenecks: str = "",
        files: List[str] | None = None,
        participants: List[Dict[str, Any]] | None = None,
        max_rounds: int = 5,
        judge_provider: str | None = None,
        debate_style: str | None = None,
    ) -> Dict[str, Any]:
        active_participants = self._normalize_participants(participants)
        bounded_rounds = max(1, min(20, int(max_rounds)))
        default_judge_provider = self.settings_service.model_role("judge")["provider"]
        normalized_judge = self._normalize_provider(judge_provider or default_judge_provider, field_name="judge_provider")
        normalized_files = self.artifact_service.normalize_inputs(files)
        resolved_style = self._resolve_style(debate_style)
        debate = self.store.create_debate(
            project_id=project_id,
            topic=topic,
            bottlenecks=bottlenecks,
            files=normalized_files,
            participants=active_participants,
            max_rounds=bounded_rounds,
            judge_provider=normalized_judge,
            debate_style=resolved_style,
        )
        return self.run_debate(debate_id=str(debate["debate_id"]), max_rounds=int(debate.get("max_rounds") or max_rounds))

    def _resolve_style(self, style: str | None) -> str:
        candidate = str(style or "").strip().lower()
        if candidate in _VALID_STYLES:
            return candidate
        stored = str(self.settings_service.get().get("debate_style") or "standard").strip().lower()
        return stored if stored in _VALID_STYLES else "standard"

    def run_debate(self, *, debate_id: str, max_rounds: int | None = None) -> Dict[str, Any]:
        debate = self.store.get_debate(debate_id)
        if debate is None:
            return {"status": "not_found", "debate_id": debate_id}
        history: List[Dict[str, str]] = []
        successful_responses = 0
        provider_errors: List[str] = []
        effective_max_rounds = max(1, min(20, int(max_rounds if max_rounds is not None else debate.get("max_rounds") or self.max_rounds)))
        for round_index in range(1, effective_max_rounds + 1):
            for participant in debate["participants"]:
                provider_name = str(participant.get("provider") or "openai").strip().lower()
                selected_model = str(participant.get("model") or self.settings_service.get().get("selected_model") or "").strip() or None
                try:
                    api_key = self.settings_service.api_key(provider_name)
                    provider = get_provider(provider_name, api_key=api_key, model=selected_model)
                    chat = ChatService(provider=provider)
                    response = chat.respond(
                        project_id=str(debate.get("project_id") or "forge"),
                        prompt=self._participant_prompt(debate=debate, history=history, round_index=round_index),
                        context={"memory_context": {"summary": self._debate_context_summary(debate)}, "checkpoints": []},
                        history=history,
                        model=selected_model,
                        api_key=api_key,
                        provider_name=provider_name,
                    )
                    response = self._normalize_round_response(response=response, provider_name=provider_name)
                except Exception as exc:
                    response = {
                        "content": f"[provider_error:{provider_name}] {exc}",
                        "provider": provider_name,
                        "model": selected_model or "",
                        "mode": "error",
                        "usage": {},
                        "error": str(exc),
                        "structured": self._fallback_round_structure(
                            content=f"[provider_error:{provider_name}] {exc}",
                            provider_name=provider_name,
                            agreed=False,
                        ),
                    }
                    provider_errors.append(f"{provider_name}: {exc}")
                self.store.add_debate_round(
                    debate_id=debate_id,
                    round_index=round_index,
                    participant_provider=provider_name,
                    participant_model=str(response.get("model") or selected_model or ""),
                    response=response,
                )
                content = str(response.get("content") or "").strip()
                history.append({"role": "assistant", "content": content})
                if str(response.get("mode") or "") != "error":
                    successful_responses += 1
                structured = response.get("structured") if isinstance(response.get("structured"), dict) else {}
                if bool(structured.get("agreed")) and str(response.get("mode") or "") != "error":
                    final = self._judge_summary(debate=debate, history=history)
                    finalized = self.store.finalize_debate(debate_id=debate_id, final_plan=final, status="completed")
                    return {"status": "ok", "debate": finalized}
        if successful_responses == 0:
            final = {
                "provider": "workspace",
                "model": None,
                "mode": "failed",
                "content": "Debate failed because all participant responses errored.",
                "usage": {},
                "errors": provider_errors,
                "structured": {
                    "plan": "Debate failed because all participant responses errored.",
                    "rationale": "Every provider call failed before a usable proposal was produced.",
                    "risks": provider_errors,
                    "confidence": 0.0,
                    "agreed": False,
                },
            }
            finalized = self.store.finalize_debate(debate_id=debate_id, final_plan=final, status="failed")
            return {"status": "ok", "debate": finalized}
        final = self._judge_summary(debate=debate, history=history)
        if provider_errors:
            final["warnings"] = provider_errors
        finalized = self.store.finalize_debate(debate_id=debate_id, final_plan=final, status="max_rounds")
        return {"status": "ok", "debate": finalized}

    def get_debate(self, *, debate_id: str) -> Dict[str, Any]:
        debate = self.store.get_debate(debate_id)
        if debate is None:
            return {"status": "not_found", "debate_id": debate_id}
        return {"status": "ok", "debate": debate}

    def list_debates(self, *, project_id: str | None = None, limit: int = 50) -> Dict[str, Any]:
        debates = self.store.list_debates(project_id=project_id, limit=limit)
        return {"status": "ok", "count": len(debates), "debates": debates}

    def _debate_context_summary(self, debate: Dict[str, Any]) -> str:
        file_labels = ", ".join(
            str(item.get("label") or item.get("path") or "").strip()
            for item in debate.get("files", [])
            if isinstance(item, dict) and str(item.get("label") or item.get("path") or "").strip()
        ) or "[none]"
        bottlenecks = str(debate.get("bottlenecks") or "").strip() or "[none]"
        return f"Debate topic: {debate.get('topic', '')}\nBottlenecks: {bottlenecks}\nFiles: {file_labels}"

    def _participant_prompt(self, *, debate: Dict[str, Any], history: List[Dict[str, str]], round_index: int) -> str:
        prior = "\n".join(f"- {item['content']}" for item in history[-4:] if str(item.get("content") or "").strip())
        files = self.artifact_service.prompt_context(debate.get("files") if isinstance(debate.get("files"), list) else [])
        style = str(debate.get("debate_style") or "standard").strip().lower()
        style_instruction = _STYLE_CONFIGS.get(style, "")
        style_line = f"Style instruction: {style_instruction}\n" if style_instruction else ""
        return (
            f"Round {round_index} debate.\n"
            f"Topic: {debate.get('topic', '')}\n"
            f"Bottlenecks:\n- {str(debate.get('bottlenecks') or '').strip() or '[none]'}\n"
            f"Artifacts:\n{files}\n"
            f"Recent positions:\n{prior or '[none]'}\n"
            f"{style_line}\n"
            "Return valid JSON only with this exact shape:\n"
            '{'
            '"proposal": "concise engineering recommendation", '
            '"rationale": "why this is the best next step", '
            '"risks": ["risk 1", "risk 2"], '
            '"confidence": 0.0, '
            '"agreed": false'
            "}\n"
            "Set agreed to true only if the group has clearly converged. Confidence must be between 0 and 1."
        )

    def _judge_summary(self, *, debate: Dict[str, Any], history: List[Dict[str, str]]) -> Dict[str, Any]:
        judge_role = self.settings_service.model_role("judge")
        judge_provider = str(debate.get("judge_provider") or judge_role["provider"]).strip().lower()
        selected_model = judge_role["model"] or str(self.settings_service.get().get("selected_model") or "").strip() or None
        latest_debate = self.store.get_debate(str(debate.get("debate_id") or "")) or debate
        structured_rounds = self._structured_history_payload(debate=latest_debate)
        try:
            api_key = self.settings_service.api_key(judge_provider)
            provider = get_provider(judge_provider, api_key=api_key, model=selected_model)
            chat = ChatService(provider=provider)
            response = chat.respond(
                project_id=str(debate.get("project_id") or "forge"),
                prompt=(
                    f"Summarize the engineering plan for this debate topic: {debate.get('topic', '')}.\n"
                    "Use the structured round data below. Do not invent new requirements.\n\n"
                    f"Structured rounds JSON:\n{json.dumps(structured_rounds, ensure_ascii=True)}\n\n"
                    "Return valid JSON only with this exact shape:\n"
                    '{'
                    '"plan": "final plan", '
                    '"rationale": "why this plan wins", '
                    '"risks": ["risk 1", "risk 2"], '
                    '"confidence": 0.0, '
                    '"agreed": false'
                    "}"
                ),
                context={"memory_context": {"summary": self._debate_context_summary(debate)}, "checkpoints": []},
                history=history,
                model=selected_model,
                api_key=api_key,
                provider_name=judge_provider,
            )
        except Exception as exc:
            return {
                "provider": "workspace",
                "model": selected_model,
                "mode": "fallback",
                "content": (
                    "Judge summary unavailable due to provider error. "
                    f"Last response: {history[-1]['content'] if history else '[none]'}"
                ),
                "usage": {},
                "error": str(exc),
                "structured": {
                    "plan": history[-1]["content"] if history else "Judge summary unavailable.",
                    "rationale": "Fell back to the latest debate response because the judge provider failed.",
                    "risks": [str(exc)],
                    "confidence": 0.2,
                    "agreed": False,
                },
            }
        normalized = self._normalize_final_plan_response(response=response, provider_name=judge_provider)
        return {
            "provider": response.get("provider", judge_provider),
            "model": response.get("model", selected_model),
            "content": normalized.get("content", ""),
            "mode": response.get("mode", "live"),
            "usage": response.get("usage", {}),
            "structured": normalized.get("structured", {}),
        }

    def _normalize_round_response(self, *, response: Dict[str, Any], provider_name: str) -> Dict[str, Any]:
        content = str(response.get("content") or "").strip()
        structured = self._parse_json_object(content)
        if structured is None:
            structured_payload = self._fallback_round_structure(
                content=content,
                provider_name=provider_name,
                agreed="AGREED" in content.upper(),
            )
        else:
            structured_payload = {
                "proposal": str(structured.get("proposal") or content or "No proposal provided.").strip(),
                "rationale": str(structured.get("rationale") or "No rationale provided.").strip(),
                "risks": self._normalize_risks(structured.get("risks")),
                "confidence": self._normalize_confidence(structured.get("confidence")),
                "agreed": bool(structured.get("agreed")),
            }
        response["structured"] = structured_payload
        response["content"] = self._render_round_content(structured_payload)
        return response

    def _normalize_final_plan_response(self, *, response: Dict[str, Any], provider_name: str) -> Dict[str, Any]:
        content = str(response.get("content") or "").strip()
        structured = self._parse_json_object(content)
        if structured is None:
            payload = {
                "plan": content or "No final plan available.",
                "rationale": "Derived from the judge response without structured fields.",
                "risks": [],
                "confidence": 0.5,
                "agreed": "AGREED" in content.upper(),
            }
        else:
            payload = {
                "plan": str(structured.get("plan") or structured.get("proposal") or content or "No final plan available.").strip(),
                "rationale": str(structured.get("rationale") or "No rationale provided.").strip(),
                "risks": self._normalize_risks(structured.get("risks")),
                "confidence": self._normalize_confidence(structured.get("confidence")),
                "agreed": bool(structured.get("agreed")),
            }
        return {
            "provider": response.get("provider", provider_name),
            "content": self._render_final_plan_content(payload),
            "structured": payload,
        }

    def _structured_history_payload(self, *, debate: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for round_item in debate.get("rounds", []):
            if not isinstance(round_item, dict):
                continue
            response = round_item.get("response") if isinstance(round_item.get("response"), dict) else {}
            structured = response.get("structured") if isinstance(response.get("structured"), dict) else {}
            rows.append(
                {
                    "round_index": int(round_item.get("round_index") or 0),
                    "provider": str(round_item.get("participant_provider") or ""),
                    "model": str(round_item.get("participant_model") or ""),
                    "proposal": str(structured.get("proposal") or response.get("content") or "").strip(),
                    "rationale": str(structured.get("rationale") or "").strip(),
                    "risks": self._normalize_risks(structured.get("risks")),
                    "confidence": self._normalize_confidence(structured.get("confidence")),
                    "agreed": bool(structured.get("agreed")),
                }
            )
        return rows

    @staticmethod
    def _parse_json_object(content: str) -> Dict[str, Any] | None:
        text = content.strip()
        if not text:
            return None
        candidates = [text]
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                cleaned = part.strip()
                if not cleaned:
                    continue
                if cleaned.lower().startswith("json"):
                    cleaned = cleaned[4:].strip()
                candidates.append(cleaned)
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    @staticmethod
    def _normalize_risks(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    @staticmethod
    def _normalize_confidence(value: Any) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = 0.5
        return max(0.0, min(1.0, numeric))

    def _fallback_round_structure(self, *, content: str, provider_name: str, agreed: bool) -> Dict[str, Any]:
        return {
            "proposal": content or f"{provider_name} returned no proposal.",
            "rationale": "Derived from an unstructured provider response.",
            "risks": [],
            "confidence": 0.5,
            "agreed": bool(agreed),
        }

    @staticmethod
    def _render_round_content(structured: Dict[str, Any]) -> str:
        risks = structured.get("risks") if isinstance(structured.get("risks"), list) else []
        risk_text = ", ".join(str(item) for item in risks if str(item).strip()) or "none"
        return (
            f"Proposal: {str(structured.get('proposal') or '').strip()}\n"
            f"Rationale: {str(structured.get('rationale') or '').strip()}\n"
            f"Risks: {risk_text}\n"
            f"Confidence: {DebateService._normalize_confidence(structured.get('confidence')):.2f}\n"
            f"Agreed: {'yes' if structured.get('agreed') else 'no'}"
        ).strip()

    @staticmethod
    def _render_final_plan_content(structured: Dict[str, Any]) -> str:
        risks = structured.get("risks") if isinstance(structured.get("risks"), list) else []
        risk_lines = "\n".join(f"- {str(item).strip()}" for item in risks if str(item).strip()) or "- none"
        return (
            f"Plan:\n{str(structured.get('plan') or '').strip()}\n\n"
            f"Rationale:\n{str(structured.get('rationale') or '').strip()}\n\n"
            f"Risks:\n{risk_lines}\n\n"
            f"Confidence: {DebateService._normalize_confidence(structured.get('confidence')):.2f}\n"
            f"Agreed: {'yes' if structured.get('agreed') else 'no'}"
        ).strip()
