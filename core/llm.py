"""
Quad-Tier LLM Engine — Multi-Model Cascading for Rail Debug.

Tier 1: Regex (handled in analyzer.py — free/instant)
Tier 2: xAI Grok Fast (cheap/fast default LLM)
Tier 3: Anthropic Claude 3.5 Haiku (mid-tier via --haiku)
Tier 4: Anthropic Claude 3.7 Sonnet (deep reasoning via --deep)
"""

import os
import json
from typing import Optional

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# Model routing table
TIER_2_MODEL = "grok-2-latest"
TIER_3_MODEL = "claude-3-5-haiku-latest"
TIER_4_MODEL = "claude-3-7-sonnet-latest"

XAI_BASE_URL = "https://api.x.ai/v1"

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

If source code context is provided alongside the traceback, use it to give a more precise root cause and fix. Reference specific variable names, logic errors, or misconfigurations visible in the code.

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

If source code context is provided, analyze the actual code logic — identify variable states, control flow issues, and architectural antipatterns visible in the surrounding lines. Reference specific code when diagnosing.

Think deeply. Trace causation chains. Identify systemic patterns. No markdown outside the JSON."""


def _get_grok_client() -> Optional[object]:
    """Initialize xAI Grok client via OpenAI SDK."""
    if OpenAI is None:
        return None
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key, base_url=XAI_BASE_URL)


def _get_anthropic_client() -> Optional[object]:
    """Initialize Anthropic client."""
    if anthropic is None:
        return None
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)


def _build_user_message(traceback_text: str, source_context: str = "") -> str:
    """Build the user message with traceback and optional source context."""
    msg = f"Analyze this traceback:\n\n```\n{traceback_text}\n```"
    if source_context:
        msg += f"\n\nSource code context (lines around the error):\n\n```\n{source_context}\n```"
    return msg


def _parse_response(response_text: str) -> dict:
    """Parse JSON from LLM response, handling markdown wrapping."""
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])
    return json.loads(text)


def _analyze_grok(traceback_text: str, source_context: str = "") -> Optional[dict]:
    """Tier 2: Grok Fast analysis."""
    client = _get_grok_client()
    if client is None:
        return None

    try:
        response = client.chat.completions.create(
            model=TIER_2_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_message(traceback_text, source_context)},
            ],
            max_tokens=1024,
        )
        result = _parse_response(response.choices[0].message.content)
        result["_tier"] = 2
        result["_model"] = TIER_2_MODEL
        return result
    except Exception as e:
        return {
            "error_type": "LLMAnalysisError",
            "error_message": str(e),
            "root_cause": f"Grok analysis failed ({type(e).__name__})",
            "suggested_fix": "Check XAI_API_KEY or retry. Falling back to regex.",
            "severity": "low",
            "_tier": 2,
            "_model": TIER_2_MODEL,
        }


def _analyze_anthropic(traceback_text: str, deep: bool = False, source_context: str = "") -> Optional[dict]:
    """Tier 3/4: Anthropic Claude analysis."""
    client = _get_anthropic_client()
    if client is None:
        return None

    model = TIER_4_MODEL if deep else TIER_3_MODEL
    system = DEEP_SYSTEM_PROMPT if deep else SYSTEM_PROMPT
    tier = 4 if deep else 3

    try:
        message = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system,
            messages=[
                {"role": "user", "content": _build_user_message(traceback_text, source_context)},
            ],
        )
        result = _parse_response(message.content[0].text)
        result["_tier"] = tier
        result["_model"] = model
        return result
    except Exception as e:
        return {
            "error_type": "LLMAnalysisError",
            "error_message": str(e),
            "root_cause": f"Claude analysis failed ({type(e).__name__})",
            "suggested_fix": "Check ANTHROPIC_API_KEY or retry.",
            "severity": "low",
            "_tier": tier,
            "_model": model,
        }


def analyze_with_llm(traceback_text: str, deep: bool = False, haiku: bool = False, source_context: str = "") -> Optional[dict]:
    """
    Quad-Tier LLM routing.

    Args:
        traceback_text: Raw traceback string
        deep: If True, use Tier 4 (Claude Sonnet — deep reasoning)
        haiku: If True, use Tier 3 (Claude Haiku — mid-tier)
        source_context: Pre-extracted source code context to inject into prompt

    Returns:
        Parsed dict with debug report fields, or None if no LLM available
    """
    if deep:
        return _analyze_anthropic(traceback_text, deep=True, source_context=source_context)

    if haiku:
        return _analyze_anthropic(traceback_text, deep=False, source_context=source_context)

    # Default: Tier 2 Grok Fast
    return _analyze_grok(traceback_text, source_context=source_context)
