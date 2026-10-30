from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import AgentProfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.json"


@dataclass(frozen=True)
class Settings:
    path: Path
    project_root: Path
    ollama_base_url: str
    ollama_timeout_seconds: int
    database_path: Path
    owner_profile_path: Path | None
    shepard: AgentProfile
    sheep: tuple[AgentProfile, ...]
    approval_required: frozenset[str]
    max_tasks_per_goal: int
    max_context_characters: int

    def agent(self, agent_id: str) -> AgentProfile:
        if agent_id == self.shepard.id:
            return self.shepard
        for profile in self.sheep:
            if profile.id == agent_id:
                return profile
        raise KeyError(f"Unknown agent: {agent_id}")


def _resolve_from_project(project_root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else project_root / path


def load_settings(path: str | Path | None = None) -> Settings:
    config_path = Path(path or os.environ.get("SHEPARD_CONFIG", DEFAULT_CONFIG_PATH)).expanduser().resolve()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    project_root = config_path.parent.parent
    shepard_raw = dict(raw["shepard"])
    shepard_raw.setdefault("capabilities", [])
    model_override = os.environ.get("SHEPARD_MODEL_OVERRIDE", "").strip()
    if model_override:
        shepard_raw["model"] = model_override
    sheep_raw = [dict(item) for item in raw.get("sheep", [])]
    if model_override:
        for profile in sheep_raw:
            profile["model"] = model_override
    policy = raw.get("policy", {})
    owner_profile = raw.get("owner_profile")
    settings = Settings(
        path=config_path,
        project_root=project_root,
        ollama_base_url=str(raw.get("ollama", {}).get("base_url", "http://127.0.0.1:11434")).rstrip("/"),
        ollama_timeout_seconds=int(raw.get("ollama", {}).get("timeout_seconds", 300)),
        database_path=_resolve_from_project(project_root, str(raw.get("database", "data/labyrinth.db"))),
        owner_profile_path=(
            _resolve_from_project(project_root, str(owner_profile)) if owner_profile else None
        ),
        shepard=AgentProfile.from_dict(shepard_raw),
        sheep=tuple(AgentProfile.from_dict(item) for item in sheep_raw),
        approval_required=frozenset(str(item) for item in policy.get("approval_required", [])),
        max_tasks_per_goal=int(policy.get("max_tasks_per_goal", 8)),
        max_context_characters=int(policy.get("max_context_characters", 24000)),
    )
    _validate(settings)
    return settings


def _validate(settings: Settings) -> None:
    if not settings.sheep:
        raise ValueError("At least one Sheep must be configured")
    ids = [settings.shepard.id, *(profile.id for profile in settings.sheep)]
    if len(ids) != len(set(ids)):
        raise ValueError("Agent IDs must be unique")
    if settings.max_tasks_per_goal < 1:
        raise ValueError("max_tasks_per_goal must be at least 1")


def update_persona(
    path: str | Path | None,
    agent_id: str,
    *,
    name: str | None = None,
    persona: str | None = None,
    model: str | None = None,
    role: str | None = None,
) -> AgentProfile:
    config_path = Path(path or os.environ.get("SHEPARD_CONFIG", DEFAULT_CONFIG_PATH)).expanduser().resolve()
    raw: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
    candidates = [raw["shepard"], *raw.get("sheep", [])]
    target = next((item for item in candidates if item.get("id") == agent_id), None)
    if target is None:
        raise KeyError(f"Unknown agent: {agent_id}")
    if name is not None:
        target["name"] = name
    if persona is not None:
        target["persona"] = persona
    if model is not None:
        target["model"] = model
    if role is not None:
        target["role"] = role

    _write_config(config_path, raw)
    return load_settings(config_path).agent(agent_id)


def _write_config(config_path: Path, raw: dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=config_path.parent, delete=False, suffix=".tmp"
    ) as handle:
        json.dump(raw, handle, indent=2)
        handle.write("\n")
        temp_path = Path(handle.name)
    os.replace(temp_path, config_path)


def add_sheep(
    path: str | Path | None,
    *,
    name: str,
    role: str,
    persona: str,
    model: str = "qwen3:8b",
) -> AgentProfile:
    config_path = Path(path or os.environ.get("SHEPARD_CONFIG", DEFAULT_CONFIG_PATH)).expanduser().resolve()
    raw: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
    sheep = raw.setdefault("sheep", [])
    if len(sheep) >= 16:
        raise ValueError("The current Labyrinth supports up to 16 Sheep")
    clean_name = name.strip()
    clean_role = role.strip()
    clean_persona = persona.strip()
    clean_model = model.strip()
    if not all((clean_name, clean_role, clean_persona, clean_model)):
        raise ValueError("Name, role, character, and model are required")
    base_id = re.sub(r"[^a-z0-9]+", "-", clean_name.lower()).strip("-") or "sheep"
    known_ids = {str(item.get("id")) for item in [raw.get("shepard", {}), *sheep]}
    agent_id = base_id
    suffix = 2
    while agent_id in known_ids:
        agent_id = f"{base_id}-{suffix}"
        suffix += 1
    sheep.append({
        "id": agent_id,
        "name": clean_name,
        "model": clean_model,
        "role": clean_role,
        "persona": clean_persona,
        "capabilities": ["local.read", "artifact.draft"],
    })
    _write_config(config_path, raw)
    return load_settings(config_path).agent(agent_id)
