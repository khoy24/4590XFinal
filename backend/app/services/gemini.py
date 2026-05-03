import json
import re
import uuid
from typing import Any

from app.config import model
from app.schemas import PendingActionItem
from app.services.aws_actions import (
    ALLOWED_AWS_ACTIONS,
    needs_user_confirmation,
    risk_summary_for_action,
    validate_allowlisted_action,
)


def parse_gemini_json(text: str) -> dict[str, Any]:
    """Extract JSON object from model output (handles optional markdown fences)."""
    s = text.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", s)
    if fence:
        s = fence.group(1).strip()
    return json.loads(s)


def partition_actions_for_chat(
    workspace_entry: dict[str, Any],
    actions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[PendingActionItem]]:
    """Split Gemini actions into those to execute immediately vs pending confirmation."""
    workspace_entry.setdefault("pending_actions", {})
    to_execute: list[dict[str, Any]] = []
    pending_items: list[PendingActionItem] = []

    for raw in actions:
        valid, service, operation, params = validate_allowlisted_action(raw)
        if not valid:
            to_execute.append(raw)
            continue
        normalized = {"service": service, "operation": operation, "params": params}
        if needs_user_confirmation(service, operation):
            action_id = str(uuid.uuid4())
            workspace_entry["pending_actions"][action_id] = {
                "service": service,
                "operation": operation,
                "params": params,
            }
            pending_items.append(
                PendingActionItem(
                    action_id=action_id,
                    service=service,
                    operation=operation,
                    params=params,
                    risk_summary=risk_summary_for_action(service, operation, params),
                )
            )
        else:
            to_execute.append(normalized)

    return to_execute, pending_items


def build_chat_full_prompt(
    account_id: str,
    region: str,
    user_prompt: str,
) -> str:
    allowed_block = "\n".join(
        f"- {svc}: {', '.join(sorted(ops))}"
        for svc, ops in sorted(ALLOWED_AWS_ACTIONS.items())
    )

    system_prompt = f"""You are a Cloud Security Architect helping a non-technical user work with AWS safely.
The user has connected via a limited IAM role assumed by our backend using STS into AWS account {account_id} (region {region}). Do not invent ARNs or credentials; rely on aws_actions below for API calls only.

You MUST respond with ONLY a single JSON object (no markdown, no backticks, no other text) with this exact shape:
{{
  "explanation": "Brief, friendly plain-English answer for the user.",
  "aws_actions": [
    {{
      "service": "s3|ec2|iam|sts",
      "operation": "exact boto3 client method name",
      "params": {{ }}
    }}
  ]
}}

If no AWS API call is needed, use "aws_actions": [].

You may ONLY use these allowed operations (service + operation):
{allowed_block}

Rules:
- Mutating operations (such as s3 create_bucket) are never run immediately by the backend. They appear as pending until the user confirms in the app. In your explanation, say what would happen and that the user must confirm — do not state the resource was already created or already changed.
- Do not include EC2 VPC networking write operations (create_vpc, subnets, gateways, route tables, routing, tags) in aws_actions. Those are only available via the Guided VPC Starter in the app UI. For questions about building a VPC, tell the user to use that flow and use describe_* operations only if they need to inspect existing resources.
- For create_bucket, include "Bucket" in params. If region is not us-east-1, add CreateBucketConfiguration with LocationConstraint equal to the region.
- For get_user, include "UserName" when the user asks about a specific user.
- Prefer read-only describe/list operations when the user only asks to view or list resources.
- Keep explanations concise."""

    return f"{system_prompt}\n\nUser request: {user_prompt}"


def generate_model_reply(full_prompt: str) -> str:
    response = model.generate_content(full_prompt)
    return (response.text or "").strip()


def parse_chat_response_text(raw_text: str) -> tuple[str, list[dict[str, Any]]]:
    """Return (explanation, aws_actions dicts). Falls back to raw_text and [] on parse failure."""
    explanation = raw_text
    actions: list[dict[str, Any]] = []
    try:
        parsed = parse_gemini_json(raw_text)
        explanation = parsed.get("explanation") or raw_text
        raw_actions = parsed.get("aws_actions")
        if isinstance(raw_actions, list):
            actions = [a for a in raw_actions if isinstance(a, dict)]
    except (json.JSONDecodeError, ValueError, TypeError):
        actions = []
    return explanation, actions
