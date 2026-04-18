"""Persona layer for MLX-Moxy-Wirks. Moxy is the default, core identity."""

from .moxy import MOXY_IDENTITY, MOXY_SYSTEM_PROMPT, compose_moxy_prompt

__all__ = ["MOXY_IDENTITY", "MOXY_SYSTEM_PROMPT", "compose_moxy_prompt"]
