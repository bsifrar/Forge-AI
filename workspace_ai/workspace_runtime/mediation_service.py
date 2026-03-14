from __future__ import annotations

from typing import Any, Dict, List

from workspace_ai.workspace_memory.session_store import SessionStore


class MediationService:
    def __init__(self, *, store: SessionStore) -> None:
        self.store = store

    def get_mediation(self, *, debate_id: str) -> Dict[str, Any]:
        debate = self.store.get_debate(debate_id)
        if debate is None:
            return {"status": "not_found", "debate_id": debate_id}
        return {"status": "ok", "mediation": self._assemble(debate=debate)}

    # ── assembly ──────────────────────────────────────────────────────────────

    def _assemble(self, *, debate: Dict[str, Any]) -> Dict[str, Any]:
        rounds = debate.get("rounds") or []
        participants = self._group_by_participant(rounds)
        final_plan = debate.get("final_plan") if isinstance(debate.get("final_plan"), dict) else {}
        judge = self._extract_judge(final_plan)
        key_differences = self._derive_key_differences(participants)
        return {
            "debate_id": str(debate.get("debate_id") or ""),
            "topic": str(debate.get("topic") or ""),
            "debate_style": str(debate.get("debate_style") or "standard"),
            "status": str(debate.get("status") or ""),
            "participants": participants,
            "judge": judge,
            "key_differences": key_differences,
            "recommended_next_step": self._recommended_next_step(debate=debate, judge=judge),
        }

    def _group_by_participant(self, rounds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen: List[str] = []
        by_provider: Dict[str, List[Dict[str, Any]]] = {}
        by_model: Dict[str, str] = {}

        for round_item in rounds:
            provider = str(round_item.get("participant_provider") or "unknown")
            model = str(round_item.get("participant_model") or "")
            if provider not in by_provider:
                seen.append(provider)
                by_provider[provider] = []
                by_model[provider] = model
            response = round_item.get("response") if isinstance(round_item.get("response"), dict) else {}
            structured = response.get("structured") if isinstance(response.get("structured"), dict) else {}
            by_provider[provider].append({
                "round_index": int(round_item.get("round_index") or 0),
                "proposal": str(structured.get("proposal") or response.get("content") or "").strip(),
                "rationale": str(structured.get("rationale") or "").strip(),
                "risks": self._normalize_risks(structured.get("risks")),
                "confidence": self._normalize_confidence(structured.get("confidence")),
                "agreed": bool(structured.get("agreed")),
            })

        result: List[Dict[str, Any]] = []
        for idx, provider in enumerate(seen):
            participant_rounds = by_provider[provider]
            latest = participant_rounds[-1] if participant_rounds else {}
            label = f"Debate {chr(ord('A') + idx)}" if idx < 26 else f"Participant {idx + 1}"
            result.append({
                "label": label,
                "provider": provider,
                "model": by_model[provider],
                "rounds": participant_rounds,
                "latest": latest,
            })
        return result

    def _extract_judge(self, final_plan: Dict[str, Any]) -> Dict[str, Any]:
        structured = final_plan.get("structured") if isinstance(final_plan.get("structured"), dict) else {}
        return {
            "provider": str(final_plan.get("provider") or "").strip(),
            "model": str(final_plan.get("model") or "").strip(),
            "plan": str(structured.get("plan") or final_plan.get("content") or "").strip(),
            "rationale": str(structured.get("rationale") or "").strip(),
            "risks": self._normalize_risks(structured.get("risks")),
            "confidence": self._normalize_confidence(structured.get("confidence")),
            "agreed": bool(structured.get("agreed")),
        }

    def _derive_key_differences(self, participants: List[Dict[str, Any]]) -> List[str]:
        if len(participants) < 2:
            return []

        diffs: List[str] = []
        a = participants[0]
        b = participants[1]
        a_latest = a.get("latest") or {}
        b_latest = b.get("latest") or {}

        # Compare proposals (first 80 chars as a quick divergence check)
        a_prop = str(a_latest.get("proposal") or "").strip()
        b_prop = str(b_latest.get("proposal") or "").strip()
        if a_prop and b_prop and a_prop[:80] != b_prop[:80]:
            a_snippet = a_prop[:120] + ("..." if len(a_prop) > 120 else "")
            b_snippet = b_prop[:120] + ("..." if len(b_prop) > 120 else "")
            diffs.append(
                f"{a['label']} proposes: {a_snippet}\n"
                f"{b['label']} proposes: {b_snippet}"
            )

        # Compare risks: symmetric differences between the two sets
        a_risks = {str(r).strip().lower() for r in (a_latest.get("risks") or []) if str(r).strip()}
        b_risks = {str(r).strip().lower() for r in (b_latest.get("risks") or []) if str(r).strip()}
        only_a = sorted(a_risks - b_risks)
        only_b = sorted(b_risks - a_risks)
        if only_a:
            diffs.append(f"Risks only from {a['label']}: {', '.join(only_a[:3])}")
        if only_b:
            diffs.append(f"Risks only from {b['label']}: {', '.join(only_b[:3])}")

        # Compare confidence (flag divergence ≥ 0.15)
        a_conf = float(a_latest.get("confidence") or 0.5)
        b_conf = float(b_latest.get("confidence") or 0.5)
        if abs(a_conf - b_conf) >= 0.15:
            diffs.append(
                f"Confidence divergence: {a['label']}={a_conf:.2f}, {b['label']}={b_conf:.2f}"
            )

        # Compare agreed state
        a_agreed = bool(a_latest.get("agreed"))
        b_agreed = bool(b_latest.get("agreed"))
        if a_agreed != b_agreed:
            agreed_label = a["label"] if a_agreed else b["label"]
            diffs.append(f"Agreement mismatch: {agreed_label} agreed; the other did not.")

        if not diffs:
            diffs.append("No significant differences detected between participants in the latest round.")
        return diffs

    def _recommended_next_step(self, *, debate: Dict[str, Any], judge: Dict[str, Any]) -> str:
        status = str(debate.get("status") or "")
        plan = str(judge.get("plan") or "").strip()
        if status in ("completed", "max_rounds") and plan:
            snippet = plan[:200] + ("..." if len(plan) > 200 else "")
            return f"Review the judge's final plan and create an execution proposal. Plan: {snippet}"
        if status == "failed":
            return "The debate failed to produce a usable plan. Review provider errors and restart."
        return "The debate is still in progress. Wait for completion before handing off."

    # ── helpers ───────────────────────────────────────────────────────────────

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
