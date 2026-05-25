from __future__ import annotations

import asyncio
import json
import logging
from typing import TypedDict

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a dental clinical note assistant for a private dental practice.
Given a dentist's post-procedure dictation transcript, produce a structured clinical \
note in the practice's standard single-textbox format.

Note format (a single text block with these fields):
CC: <chief complaint or reason for visit>
Anesthesia: <agent used and dose, or "None">
Treatment: <procedure performed with CDT code in parentheses, tooth number if known>
Next visit: <follow-up plan>

Rules:
- Extract tooth numbers, CDT codes, and surface notation from the transcript
- Common shorthand: "two carpules" = 3.4 mL lidocaine; "one carpule" = 1.7 mL
- Use concise, third-person clinical language — no first-person
- If a field is unclear from the transcript, use a short placeholder like "tooth #___"
- Detect the best-fit template type from: exam, prophy, extraction, crown_prep,
  crown_seat, root_canal, filling, srp, other

Example output for a filling:
CC: Restoration
Anesthesia: Lidocaine 2% 1:100,000 epinephrine, 1.7 mL
Treatment: Composite restoration (D2391) on tooth #14, MO surfaces. \
Local anesthesia administered. Decay removed. Composite placed and cured. \
Occlusion checked and adjusted.
Next visit: Routine recall.\
"""

_TOOLS = [
    {
        "name": "format_clinical_note",
        "description": "Format a dental clinical note from a dictation transcript",
        "input_schema": {
            "type": "object",
            "properties": {
                "draft": {
                    "type": "string",
                    "description": (
                        "The formatted clinical note text"
                        " in CC/Anesthesia/Treatment/Next visit format"
                    ),
                },
                "detected_template": {
                    "type": "string",
                    "enum": [
                        "exam", "prophy", "extraction", "crown_prep",
                        "crown_seat", "root_canal", "filling", "srp", "other",
                    ],
                    "description": "Best-fit template type for this procedure",
                },
            },
            "required": ["draft", "detected_template"],
        },
    }
]


class DraftResult(TypedDict):
    draft: str
    detected_template: str | None


class BedrockExtractionError(Exception):
    pass


def _invoke_sync(transcript: str, template_hint: str | None) -> DraftResult:
    settings = get_settings()
    client = boto3.client("bedrock-runtime", region_name=settings.bedrock_region)

    hint_clause = f"\nTemplate hint: {template_hint}" if template_hint else ""
    user_content = f"Dictation transcript:{hint_clause}\n\n{transcript}"

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 512,
        "system": [
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": [{"role": "user", "content": user_content}],
        "tools": _TOOLS,
        "tool_choice": {"type": "any"},
    }

    try:
        response = client.invoke_model(
            modelId=settings.bedrock_model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
    except (BotoCoreError, ClientError) as exc:
        raise BedrockExtractionError(f"Bedrock call failed: {exc}") from exc

    result = json.loads(response["body"].read())

    for block in result.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == "format_clinical_note":
            inp = block["input"]
            return DraftResult(
                draft=inp["draft"],
                detected_template=inp.get("detected_template"),
            )

    raise BedrockExtractionError("Bedrock response contained no tool_use block")


async def draft_note(transcript: str, template_hint: str | None = None) -> DraftResult:
    """Extract a structured clinical note draft from a transcript via Bedrock Haiku."""
    return await asyncio.to_thread(_invoke_sync, transcript, template_hint)
