from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    tool_name: str
    risk_level: str
    requires_approval: bool
    input_schema: dict[str, Any]


@dataclass
class ToolContext:
    settings: dict[str, Any]
    profile: dict[str, Any] | None = None


@dataclass
class ToolResult:
    success: bool
    output: str
    error: str | None = None


class BaseTool:
    spec: ToolSpec

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        raise NotImplementedError


async def run_command(
    args: list[str],
    *,
    input_text: str | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    def _run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            input=input_text,
            check=check,
            text=True,
            capture_output=True,
        )

    return await asyncio.to_thread(_run)
