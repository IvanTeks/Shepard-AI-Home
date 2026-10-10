from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import load_settings, update_persona
from .database import Labyrinth
from .ollama import OllamaClient, OllamaError
from .providers import (
    AnthropicError, GeminiError, is_claude_model, is_external_model, is_gemini_model,
    load_anthropic_api_key, load_gemini_api_key,
)
from .runtime import ShepardRuntime


def _settings_and_db(config: str | None):
    settings = load_settings(config)
    db = Labyrinth(settings.database_path)
    db.initialize()
    return settings, db


def _print_job(job: dict) -> None:
    print(f"Job: {job['id']}")
    print(f"Status: {job['status']}")
    print(f"Goal: {job['goal']}")
    if job.get("plan_summary"):
        print(f"Plan: {job['plan_summary']}")
    print("\nTasks:")
    if not job["tasks"]:
        print("  (none)")
    for task in job["tasks"]:
        print(f"  {task['position']}. [{task['status']}] {task['sheep_id']}: {task['title']}")
        if task.get("result"):
            preview = task["result"].replace("\n", " ")[:180]
            print(f"     {preview}{'…' if len(task['result']) > 180 else ''}")
    if job["approvals"]:
        print("\nApprovals:")
        for approval in job["approvals"]:
            print(f"  {approval['id']} [{approval['status']}] {approval['capability']}")
    if job.get("final_output"):
        print("\nShepard:\n")
        print(job["final_output"])
    if job.get("error"):
        print(f"\nError: {job['error']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shepard", description="Local AI agent ecosystem")
    parser.add_argument("--config", help="Path to a Shepard JSON configuration")
    parser.add_argument("--version", action="version", version=f"Shepard {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize the Labyrinth database")
    sub.add_parser("doctor", help="Check configuration and Ollama models")
    sub.add_parser("agents", help="List Shepard and the registered Sheep")

    run = sub.add_parser("run", help="Give Shepard a goal")
    run.add_argument("goal", help="The outcome Shepard should coordinate")
    run.add_argument("--json", action="store_true", help="Print the result as JSON")

    council = sub.add_parser("council", help="Gather every Sheep for the weekly improvement council")
    council.add_argument("--json", action="store_true", help="Print the result as JSON")

    jobs = sub.add_parser("jobs", help="List recent jobs")
    jobs.add_argument("--limit", type=int, default=20)

    show = sub.add_parser("show", help="Inspect a job and its work")
    show.add_argument("job_id")
    show.add_argument("--json", action="store_true")

    persona = sub.add_parser("persona", help="Update an agent's character or model")
    persona.add_argument("agent_id")
    persona.add_argument("--name")
    persona.add_argument("--persona")
    persona.add_argument("--model")

    approve = sub.add_parser("approve", help="Record an approval decision")
    approve.add_argument("approval_id")
    approve.add_argument("--deny", action="store_true")

    web = sub.add_parser("web", help="Launch the local web control center")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--no-open", action="store_true", help="Do not open a browser automatically")

    sub.add_parser("desktop", help="Launch the native desktop control room")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings, db = _settings_and_db(args.config)

        if args.command == "init":
            print(f"Labyrinth initialized: {settings.database_path}")
            return 0

        if args.command == "doctor":
            client = OllamaClient(settings.ollama_base_url, settings.ollama_timeout_seconds)
            models = client.list_models()
            configured_models = {settings.shepard.model, *(profile.model for profile in settings.sheep)}
            required = {model for model in configured_models if not is_external_model(model)}
            claude_required = sorted(model for model in configured_models if is_claude_model(model))
            gemini_required = sorted(model for model in configured_models if is_gemini_model(model))
            missing = sorted(required.difference(models))
            print(f"Configuration: OK ({settings.path})")
            print(f"Labyrinth: OK ({settings.database_path})")
            print(f"Ollama: OK ({settings.ollama_base_url})")
            print(f"Installed models: {', '.join(models) or '(none)'}")
            if missing:
                print(f"Missing required models: {', '.join(missing)}", file=sys.stderr)
                return 2
            if claude_required and not load_anthropic_api_key(settings):
                print("Missing Claude API connection for configured Claude models", file=sys.stderr)
                return 2
            if claude_required:
                print(f"Claude models configured: {', '.join(claude_required)}")
            if gemini_required and not load_gemini_api_key(settings):
                print("Missing Gemini API connection for configured Gemini models", file=sys.stderr)
                return 2
            if gemini_required:
                print(f"Gemini models configured: {', '.join(gemini_required)}")
            print("Required models: OK")
            return 0

        if args.command == "agents":
            for profile in (settings.shepard, *settings.sheep):
                kind = "SHEPARD" if profile.id == settings.shepard.id else "SHEEP"
                print(f"{kind:<7} {profile.id:<10} {profile.name:<14} {profile.model}")
                print(f"        {profile.role}")
                print(f"        Character: {profile.persona}")
            return 0

        if args.command == "run":
            result = ShepardRuntime(settings, labyrinth=db).run(args.goal)
            if args.json:
                print(json.dumps({
                    "job_id": result.job_id,
                    "status": result.status,
                    "final_output": result.final_output,
                    "approval_ids": result.approval_ids,
                }, indent=2))
            else:
                print(f"Job: {result.job_id}")
                print(f"Status: {result.status}\n")
                print(result.final_output)
                if result.approval_ids:
                    print("\nPending approvals:")
                    for approval_id in result.approval_ids:
                        print(f"  {approval_id}")
            return 0

        if args.command == "council":
            result = ShepardRuntime(settings, labyrinth=db).run_council()
            if args.json:
                print(json.dumps({
                    "job_id": result.job_id,
                    "status": result.status,
                    "final_output": result.final_output,
                }, indent=2))
            else:
                print(f"Council job: {result.job_id}")
                print(f"Status: {result.status}\n")
                print(result.final_output)
            return 0

        if args.command == "jobs":
            for job in db.list_jobs(max(1, args.limit)):
                print(f"{job['id']}  {job['status']:<18} {job['created_at']}  {job['goal'][:72]}")
            return 0

        if args.command == "show":
            job = db.get_job(args.job_id)
            print(json.dumps(job, indent=2) if args.json else "", end="" if args.json else "")
            if not args.json:
                _print_job(job)
            else:
                print()
            return 0

        if args.command == "persona":
            if args.name is None and args.persona is None and args.model is None:
                parser = build_parser()
                parser.error("persona requires --name, --persona, or --model")
            profile = update_persona(
                args.config, args.agent_id, name=args.name, persona=args.persona, model=args.model
            )
            print(f"Updated {profile.id}: {profile.name} ({profile.model})")
            print(f"Character: {profile.persona}")
            return 0

        if args.command == "approve":
            decision = "denied" if args.deny else "approved"
            db.decide_approval(args.approval_id, decision)
            print(f"{args.approval_id}: {decision}")
            print("Decision recorded. Connector execution is intentionally disabled in version 0.1.")
            return 0

        if args.command == "web":
            from .webapp import serve
            serve("127.0.0.1", args.port, args.config, open_browser=not args.no_open)
            return 0

        if args.command == "desktop":
            from .desktop import launch
            launch(args.config)
            return 0

        return 1
    except (FileNotFoundError, KeyError, ValueError, OllamaError, AnthropicError, GeminiError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
