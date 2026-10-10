from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentProfile:
    id: str
    name: str
    model: str
    role: str
    persona: str
    capabilities: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AgentProfile":
        return cls(
            id=str(value["id"]),
            name=str(value["name"]),
            model=str(value["model"]),
            role=str(value["role"]),
            persona=str(value.get("persona", "")),
            capabilities=tuple(str(item) for item in value.get("capabilities", [])),
        )


@dataclass(frozen=True)
class PlannedTask:
    sheep_id: str
    title: str
    instructions: str
    required_capability: str | None = None


@dataclass(frozen=True)
class Plan:
    summary: str
    tasks: tuple[PlannedTask, ...]


@dataclass(frozen=True)
class RunResult:
    job_id: str
    status: str
    final_output: str
    approval_ids: tuple[str, ...] = field(default_factory=tuple)
