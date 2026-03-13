from __future__ import annotations

import argparse
import json
import sys

from workspace_ai.workspace_terminal.client import APIClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Standalone workspace terminal client")
    parser.add_argument("--base-url", default="http://127.0.0.1:8092")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-session")
    create.add_argument("project_id")
    create.add_argument("--title", default="")
    create.add_argument("--mode", default="chat")
    settings = sub.add_parser("settings")
    settings.add_argument("--api-enabled", choices=["true", "false"], default=None)
    settings.add_argument("--model", default=None)
    settings.add_argument("--daily-cap", type=float, default=None)
    settings.add_argument("--hourly-cap", type=int, default=None)
    settings.add_argument("--input-price", type=float, default=None)
    settings.add_argument("--output-price", type=float, default=None)
    send = sub.add_parser("send")
    send.add_argument("session_id")
    send.add_argument("content")
    send.add_argument("--stream", action="store_true")
    send.add_argument("--token-budget", type=int, default=1800)
    send.add_argument("--model", default=None)
    imports = sub.add_parser("list-imports")
    imports.add_argument("--project-id", default=None)
    resume = sub.add_parser("resume-chatgpt")
    resume.add_argument("query")
    resume.add_argument("--project-id", default=None)
    resume.add_argument("--send", default=None)
    resume.add_argument("--stream", action="store_true")
    resume.add_argument("--token-budget", type=int, default=1800)
    resume.add_argument("--model", default=None)
    imp = sub.add_parser("import-chatgpt")
    imp.add_argument("project_id")
    imp.add_argument("export_path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = APIClient(base_url=args.base_url)
    if args.command == "create-session":
        payload = client.post("/workspace/sessions", {"project_id": args.project_id, "title": args.title, "mode": args.mode})
    elif args.command == "settings":
        if any(
            value is not None
            for value in [args.api_enabled, args.model, args.daily_cap, args.hourly_cap, args.input_price, args.output_price]
        ):
            payload = client.post(
                "/workspace/settings",
                {
                    "api_enabled": None if args.api_enabled is None else args.api_enabled == "true",
                    "selected_model": args.model,
                    "daily_spend_cap_usd": args.daily_cap,
                    "hourly_call_cap": args.hourly_cap,
                    "price_input_per_1m_usd": args.input_price,
                    "price_output_per_1m_usd": args.output_price,
                },
            )
        else:
            payload = client.get("/workspace/settings")
    elif args.command == "send":
        if args.stream:
            for event in client.post_stream(f"/workspace/sessions/{args.session_id}/messages/stream", {"content": args.content, "token_budget": args.token_budget, "model": args.model}):
                if event.get("type") == "workspace.response.delta":
                    sys.stdout.write(str(event.get("delta") or ""))
                    sys.stdout.flush()
                else:
                    sys.stdout.write("\n")
                    json.dump(event, sys.stdout, indent=2, sort_keys=True)
                    sys.stdout.write("\n")
            return 0
        payload = client.post(f"/workspace/sessions/{args.session_id}/messages", {"content": args.content, "token_budget": args.token_budget, "model": args.model})
    elif args.command == "list-imports":
        payload = client.get("/workspace/imports", {"project_id": args.project_id} if args.project_id else None)
    elif args.command == "resume-chatgpt":
        resume_payload = client.post("/workspace/imports/resume", {"query": args.query, "project_id": args.project_id})
        if args.send and resume_payload.get("status") == "ok":
            session_id = str(resume_payload.get("matched_session", {}).get("session_id", ""))
            if args.stream:
                streamed = []
                for event in client.post_stream(f"/workspace/sessions/{session_id}/messages/stream", {"content": args.send, "token_budget": args.token_budget, "model": args.model}):
                    streamed.append(event)
                    if event.get("type") == "workspace.response.delta":
                        sys.stdout.write(str(event.get("delta") or ""))
                        sys.stdout.flush()
                sys.stdout.write("\n")
                payload = {"status": "ok", "resume": resume_payload, "send": {"status": "ok", "streamed_events": streamed}}
            else:
                payload = {"status": "ok", "resume": resume_payload, "send": client.post(f"/workspace/sessions/{session_id}/messages", {"content": args.send, "token_budget": args.token_budget, "model": args.model})}
        else:
            payload = resume_payload
    elif args.command == "import-chatgpt":
        payload = client.post("/workspace/import/chatgpt-export", {"project_id": args.project_id, "export_path": args.export_path})
    else:
        return 1
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
