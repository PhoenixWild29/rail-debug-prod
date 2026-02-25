"""
Tri-State LLM Engine — Anthropic Claude integration for Rail Debug.

Tier 1: Regex (handled in analyzer.py — free/instant)
Tier 2: Claude 4.5 Haiku — cheap/fast for standard unknowns
Tier 3: Claude 4.6 Sonnet/Opus — deep architectural reasoning (--deep flag)
"""

import os
import json
from typing import Optional

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


TIER_2_MODEL = "claude-haiku-4-5-20250710"
TIER_3_MODEL = os.getenv("RAIL_DEBUG_DEEP_MODEL", "claude-sonnet-4-6-20250514")

SYSTEM_PROMPT = """You are Rail Debug, an expert AI debugging engine. Analyze the Python traceback provided and return ONLY a JSON object with these exact keys:

{
  "error_type": "the exception class name",
  "error_message": "the error message",
  "file_path": "file where error originated or null",
  "line_number": line number as integer or null,
  "function_name": "function name or null",
  "root_cause": "concise root cause explanation",
  "suggested_fix": "actionable fix with code snippet if relevant",
  "severity": "low|medium|high|critical"
}

Be precise. Be actionable. No markdown, no explanation outside the JSON."""

DEEP_SYSTEM_PROMPT = """You are Rail Debug in DEEP ANALYSIS mode. You are an elite debugging architect. Analyze the Python traceback and return ONLY a JSON object with these exact keys:

{
  "error_type": "the exception class name",
  "error_message": "the error message",
  "file_path": "file where error originated or null",
  "line_number": line number as integer or null,
  "function_name": "function name or null",
  "root_cause": "thorough root cause analysis — trace the full chain of causation",
  "suggested_fix": "detailed fix with code examples, edge cases to watch, and architectural recommendations",
  "severity": "low|medium|high|critical",
  "architecture_notes": "broader systemic issues this error reveals, if any"
}

Think deeply. Trace causation chains. Identify systemic patterns. No markdown outside the JSON."""


def _get_client() -> Optional[object]:
    """Initialize Anthropic client. Returns None if unavailable."""
    if anthropic is None:
        return None
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)


def analyze_with_llm(traceback_text: str, deep: bool = False) -> Optional[dict]:
    """
    Send traceback to Claude for analysis.
    
    Args:
        traceback_text: Raw traceback string
        deep: If True, use Tier 3 (Sonnet/Opus) with deep analysis prompt
        
    Returns:
        Parsed dict with debug report fields, or None if LLM unavailable
    """
    client = _get_client()
    if client is None:
        return None

    model = TIER_3_MODEL if deep else TIER_2_MODEL
    system = DEEP_SYSTEM_PROMPT if deep else SYSTEM_PROMPT

    try:
        message = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system,
            messages=[
                {"role": "user", "content": f"Analyze this traceback:\n\n```\n{traceback_text}\n```"}
            ],
        )

        # Extract text content
        response_text = message.content[0].text.strip()

        # Parse JSON — handle potential markdown wrapping
        if response_text.startswith("```"):
            lines = response_text.splitlines()
            response_text = "\n".join(lines[1:-1])

        result = json.loads(response_text)
        result["_tier"] = 3 if deep else 2
        result["_model"] = model
        return result

    except (json.JSONDecodeError, anthropic.APIError, IndexError, KeyError) as e:
        return {
            "error_type": "LLMAnalysisError",
            "error_message": str(e),
            "root_cause": f"LLM analysis failed ({type(e).__name__})",
            "suggested_fix": "Check API key, network, or retry. Falling back to regex.",
            "severity": "low",
            "_tier": 3 if deep else 2,
            "_model": model,
        }
