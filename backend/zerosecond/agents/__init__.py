"""Agents: Editor (select + angle), Writer (versions), Verifier (fact check), Recap.

Two interchangeable back ends:
- ``foundry``: Microsoft Agent Framework agents on Microsoft Foundry, using the
  Zero Second MCP server for stats/memory tools.
- ``local``: deterministic template writer, so the system runs with no cloud access.
The Verifier's numeric/name check is always code and runs on both.
"""
