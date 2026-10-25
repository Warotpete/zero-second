"""Tests always use the deterministic local writer, never a real model."""
import os

os.environ["ZS_LLM"] = "local"
