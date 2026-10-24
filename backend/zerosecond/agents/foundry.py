"""Microsoft Agent Framework agents running on Microsoft Foundry.

Enabled when FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL are set (see .env.example).
Authentication uses DefaultAzureCredential: `az login` locally, managed identity on
Azure Container Apps.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

log = logging.getLogger("zerosecond.foundry")

EDITOR_PROMPT = """You are the Editor agent of Zero Second, a newsroom system for football broadcasters.
Story Radar (a statistical model) has flagged a storyline that may happen in the live match.
Use the Zero Second MCP tools to look up context (player arcs, milestones, head-to-head, recent xG) if useful.
Decide the editorial angle in one short sentence and whether content should be prepared now.
Reply with JSON only: {"prepare": true|false, "angle": "<one sentence>"}.
Never invent statistics."""

WRITER_PROMPT = """You are the Writer agent of Zero Second. You pre-write broadcast and social content for a football
storyline BEFORE it happens, so a producer can approve it in advance.
Rules:
- Use ONLY numbers, names and facts from the facts pack. Do not add any other number or player.
- You may use the live slots listed in the request; they are filled automatically at the moment it happens.
  Write slots literally with braces, e.g. "in the {minute_ord} minute".
- Write for when the storyline HAS happened (past/present tense).
- Versions: en_analyst (1-2 sentences, data-rich, measured), en_casual (one punchy line for fans),
  th_casual (natural Thai for Thai fans, with an English "gloss" translation), overlay (UPPERCASE headline
  under 40 characters and a short UPPERCASE sub line).
Reply with JSON only:
{"versions":[{"key":"en_analyst","text":"..."},{"key":"en_casual","text":"..."},
{"key":"th_casual","text":"...","gloss":"..."},{"key":"overlay","text":"HEADLINE","sub":"SUB"}]}"""

VERIFIER_PROMPT = """You are the Verifier agent of Zero Second. Check whether every claim in the draft is supported by the
facts pack. Numbers are already checked by code; focus on meaning: wrong player, wrong team, wrong direction
(e.g. 'won' vs 'lost'), claims not in the facts. Live slots in braces are fine.
Reply with JSON only: {"ok": true|false, "issues": ["..."]}."""

RECAP_PROMPT = """You are the Recap agent of Zero Second. Write three full-time recaps from the verified lifecycle log:
broadcaster (3-4 sentences, keep the [ref] citation tags after the facts they support), casual (2 sentences, warm),
analyst (2-3 sentences with the numbers given). Use only facts provided.
Reply with JSON only: {"broadcaster":"...","casual":"...","analyst":"..."}."""


def enabled() -> bool:
    mode = os.getenv("ZS_LLM", "auto").lower()
    if mode == "local":
        return False
    return bool(os.getenv("FOUNDRY_PROJECT_ENDPOINT") and os.getenv("FOUNDRY_MODEL"))


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in reply")
    return json.loads(m.group(0))


def _tool_calls(resp: Any) -> list[str]:
    """Names of tool calls made during an agent run (for the Agent Trace)."""
    names: list[str] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            if x.get("type") in ("function_call", "mcp_server_tool_call") and x.get("name"):
                args = x.get("arguments")
                names.append(f"{x['name']}({_short_args(args)})")
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    try:
        walk(resp.to_dict())
    except Exception:  # pragma: no cover - defensive
        pass
    return names


def _short_args(args: Any) -> str:
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return args[:40]
    if isinstance(args, dict):
        return ",".join(str(v) for v in args.values())[:40]
    return ""


class FoundryAgents:
    """Holds the four agents and the MCP connection for the app's lifetime."""

    def __init__(self, mcp_url: str | None):
        self.mcp_url = mcp_url
        self.timeout = float(os.getenv("ZS_AGENT_TIMEOUT", "40"))
        self._ready = False
        self._mcp = None
        self.model = os.getenv("FOUNDRY_MODEL", "")

    async def start(self) -> None:
        from agent_framework import Agent, MCPStreamableHTTPTool
        from agent_framework.foundry import FoundryChatClient
        from azure.identity.aio import DefaultAzureCredential

        self._cred = DefaultAzureCredential()
        client = FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=self._cred,
        )
        tools = []
        if self.mcp_url:
            try:
                self._mcp = MCPStreamableHTTPTool(name="zerosecond", url=self.mcp_url, load_prompts=False)
                await self._mcp.__aenter__()
                tools = [self._mcp]
            except Exception as exc:  # the Editor still works without tools
                log.warning("MCP tool unavailable: %s", exc)
                self._mcp = None
        self.editor = Agent(client, EDITOR_PROMPT, name="Editor", tools=tools)
        self.writer = Agent(client, WRITER_PROMPT, name="Writer")
        self.verifier = Agent(client, VERIFIER_PROMPT, name="Verifier")
        self.recapper = Agent(client, RECAP_PROMPT, name="Recap")
        self._ready = True

    async def stop(self) -> None:
        if self._mcp is not None:
            try:
                await self._mcp.__aexit__(None, None, None)
            except Exception:  # pragma: no cover
                pass
        if getattr(self, "_cred", None) is not None:
            await self._cred.close()

    async def _run(self, agent: Any, prompt: str) -> tuple[dict, list[str]]:
        resp = await asyncio.wait_for(agent.run(prompt), timeout=self.timeout)
        return _json(resp.text), _tool_calls(resp)

    async def edit(self, room: str, facts: dict) -> tuple[dict, list[str]]:
        prompt = (
            f"Room id for MCP tools: {room}\nStoryline facts pack:\n{json.dumps(facts, ensure_ascii=False)}\n"
            "Decide the angle."
        )
        return await self._run(self.editor, prompt)

    async def write(self, facts: dict, angle: str, feedback: list[str] | None = None) -> dict:
        slots = ", ".join("{" + s + "}" for s in facts.get("slots", []))
        prompt = (
            f"Live slots you may use: {slots}\nEditorial angle: {angle}\n"
            f"Facts pack:\n{json.dumps(facts, ensure_ascii=False)}\n"
        )
        if feedback:
            prompt += "Your previous draft was REJECTED by the Verifier for: " + "; ".join(feedback) + "\nFix these issues.\n"
        data, _ = await self._run(self.writer, prompt)
        return data

    async def check(self, facts: dict, draft: dict) -> dict:
        prompt = f"Facts pack:\n{json.dumps(facts, ensure_ascii=False)}\nDraft:\n{json.dumps(draft, ensure_ascii=False)}"
        data, _ = await self._run(self.verifier, prompt)
        return data

    async def recap(self, payload: dict) -> dict:
        prompt = f"Verified lifecycle log and match facts:\n{json.dumps(payload, ensure_ascii=False)}"
        data, _ = await self._run(self.recapper, prompt)
        return data
