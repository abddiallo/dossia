"""
Accès optionnel à un modèle d'IA (API Claude d'Anthropic).
Sans clé ANTHROPIC_API_KEY, toutes les fonctions renvoient None et l'application
bascule sur ses heuristiques : elle reste utilisable de bout en bout.
Doc : https://docs.claude.com/en/api/overview
"""
from __future__ import annotations

import json
import logging
import os
import re

log = logging.getLogger("dossia.llm")
MODEL = os.environ.get("DOSSIA_LLM_MODEL", "claude-sonnet-5-5")
_client = None


def available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    return _client


def complete_text(system: str, user: str, max_tokens: int = 2000) -> str | None:
    if not available():
        return None
    try:
        msg = _get_client().messages.create(
            model=MODEL, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    except Exception as e:  # noqa: BLE001 — l'IA ne doit jamais bloquer le parcours
        log.warning("Appel IA échoué : %s", e)
        return None


def complete_json(system: str, user: str, schema_hint: str, max_tokens: int = 6000):
    """Demande une réponse JSON stricte ; renvoie l'objet Python ou None."""
    out = complete_text(
        system + "\n\nRéponds UNIQUEMENT avec un JSON valide, sans texte autour, de la forme :\n" + schema_hint,
        user, max_tokens=max_tokens,
    )
    if not out:
        return None
    m = re.search(r"\{.*\}|\[.*\]", out, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        log.warning("JSON IA invalide")
        return None
