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
Decide the editorial angle in one short sentence and whether content should be prepared now. The angle should say why the
storyline matters (history, milestone, rivalry), not describe live match statistics.
Reply with JSON only: {"prepare": true|false, "angle": "<one sentence>"}.
Never invent statistics."""

WRITER_PROMPT = """You are the Writer agent of Zero Second. You pre-write broadcast and social content for a football
storyline BEFORE it happens, so a producer can approve it in advance.
Rules:
- Use ONLY numbers, names and facts from the facts pack. Do not add any other number or player.
- You may use the live slots listed in the request; they are filled automatically at the moment it happens.
  Write slots literally with braces, e.g. "in the {minute_ord} minute".
- Write for when the storyline HAS happened (past/present tense).
- Do not describe the match situation (who leads, equaliser, winner) unless the facts pack says it; show the
  score only through the {score} slot.
- Do not mention probabilities, forecasts or models in the copy.
- The editorial angle is guidance on tone and emphasis only: never copy numbers, shots, xG or match events from it.
- Versions: en_analyst (1-2 sentences, data-rich, measured), en_casual (one punchy line for fans),
  th_casual (natural Thai for Thai fans, with an English "gloss" translation), overlay (UPPERCASE headline
  under 40 characters and a short UPPERCASE sub line).
Reply with JSON only:
{"versions":[{"key":"en_analyst","text":"..."},{"key":"en_casual","text":"..."},
{"key":"th_casual","text":"...","gloss":"..."},{"key":"overlay","text":"HEADLINE","sub":"SUB"}]}"""

VERIFIER_PROMPT = """You are the Verifier agent of Zero Second. The draft is PRE-WRITTEN content that will only be
published at the moment the storyline in the facts pack happens. So judge it as if the storyline has just happened:
values such as club_goals_now or streak_before are the state BEFORE the moment, and `target` is the value AFTER it
(e.g. club_goals_now 49, target 50 -> "his 50th club goal" is correct). Live slots in braces are filled from match
data later and are always fine. Numbers are already checked by code.
Reject only real problems of meaning: wrong player or team, a claim about the match situation that the facts do not
support (e.g. "put them ahead", "won it"), wrong direction (won vs lost), invented events, or mentions of
probabilities/models. Ignore style.
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


def _for_writer(facts: dict) -> dict:
    """The Writer writes for the moment it happens, so it must not see the live match state."""
    return {k: v for k, v in facts.items() if k not in ("why_now", "score_now")}


class FoundryAgents:
    """Holds the four agents and the MCP connection for the app's lifetime."""

    def __init__(self, mcp_url: str | None):
        self.mcp_url = mcp_url
        self.timeout = float(os.getenv("ZS_AGENT_TIMEOUT", "40"))
        self._ready = False
        self._mcp = None
        self.model = os.getenv("FOUNDRY_MODEL", "")

    async def start(self) -> None:
        from agent_framework import Agent
        from agent_framework.foundry import FoundryChatClient
        from azure.identity.aio import DefaultAzureCredential

        self._cred = DefaultAzureCredential()
        client = FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=self._cred,
        )
        # reasoning models (e.g. gpt-5-mini): low effort keeps each agent call to a few seconds
        effort = os.getenv("ZS_REASONING_EFFORT", "low")
        opts = {"reasoning": {"effort": effort}} if effort != "off" else None
        self.editor = Agent(client, EDITOR_PROMPT, name="Editor", default_options=opts)
        self.writer = Agent(client, WRITER_PROMPT, name="Writer", default_options=opts)
        self.verifier = Agent(client, VERIFIER_PROMPT, name="Verifier", default_options=opts)
        self.recapper = Agent(client, RECAP_PROMPT, name="Recap", default_options=opts)
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
        mcp = await self._mcp_tool()
        resp = await asyncio.wait_for(self.editor.run(prompt, tools=[mcp] if mcp else None), timeout=self.timeout)
        return _json(resp.text), _tool_calls(resp)

    async def _mcp_tool(self):
        """Connect to our own MCP server on first use (it isn't listening yet during startup)."""
        if self._mcp is None and self.mcp_url and not getattr(self, "_mcp_failed", False):
            from agent_framework import MCPStreamableHTTPTool

            try:
                tool = MCPStreamableHTTPTool(name="zerosecond", url=self.mcp_url, load_prompts=False)
                await asyncio.wait_for(tool.__aenter__(), timeout=15)
                self._mcp = tool
            except Exception as exc:  # the Editor still works without tools
                log.warning("MCP tool unavailable: %s", exc)
                self._mcp_failed = True
        return self._mcp

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
