import re
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from app.deps import get_active_aws_connection, get_current_user
from app.models import AwsConnection, User
from app.schemas import (
    ActionResultItem,
    ChatRequest,
    ChatResponse,
    ConfirmActionRequest,
    ConfirmActionResponse,
    PendingPlanItem,
)
from app.services.aws_actions import (
    ALLOWED_AWS_ACTIONS,
    execute_aws_actions,
    needs_user_confirmation,
)
from app.services.credential_manager import get_execution_entry
from app.services.ec2_starter import (
    security_plan_text_ec2_starter,
    validate_ec2_starter_inputs,
)
from app.services.gemini import (
    build_chat_full_prompt,
    generate_model_reply,
    parse_chat_response_text,
    partition_actions_for_chat,
)
from app.state import workspace_for_user

router = APIRouter()

_EC2_CREATE_RE = re.compile(
    r"\b(create|launch|provision|make|spin\s+up|start)\b.*\b(ec2|instance|server|vm)\b",
    re.IGNORECASE,
)
_NAME_RE = re.compile(r"\b(?:named|called|name(?:d)?\s+as)\s+['\"]?([A-Za-z0-9._-]+)", re.IGNORECASE)
_INSTANCE_TYPE_RE = re.compile(r"\b([a-z]\d[a-z]?\.[a-z0-9]+)\b", re.IGNORECASE)
_RESOURCE_WORDS = {
    "a",
    "an",
    "ec2",
    "instance",
    "ip",
    "named",
    "please",
    "private",
    "public",
    "server",
    "the",
    "vm",
    "with",
}


def _extract_name(prompt: str, fallback: str) -> str:
    match = _NAME_RE.search(prompt)
    if match:
        return match.group(1)
    match = re.search(r"\b(?:bucket|instance|server|vm)\s+['\"]?([A-Za-z0-9._-]+)", prompt, re.IGNORECASE)
    if match:
        candidate = match.group(1)
        if (
            candidate.lower() not in _RESOURCE_WORDS
            and not _INSTANCE_TYPE_RE.fullmatch(candidate)
        ):
            return candidate
    return fallback


def _starter_plan_from_chat(
    prompt: str,
    region: str,
    ws: dict[str, Any],
) -> tuple[str, PendingPlanItem] | None:
    text = prompt.strip()
    if _EC2_CREATE_RE.search(text):
        instance_type_match = _INSTANCE_TYPE_RE.search(text)
        instance_type = instance_type_match.group(1) if instance_type_match else "t3.micro"
        assign_public_ip = bool(re.search(r"\bpublic\s+ip\b|\bpublic\b", text, re.IGNORECASE))
        validated = validate_ec2_starter_inputs(
            _extract_name(text, "demo-instance"),
            instance_type,
            assign_public_ip,
            region,
        )
        plan_id = str(uuid.uuid4())
        inputs = {
            "instance_name": validated["instance_name"],
            "region": validated["region"],
            "instance_type": validated["instance_type"],
            "assign_public_ip": validated["assign_public_ip"],
        }
        ws.setdefault("pending_plans", {})[plan_id] = {
            "kind": "ec2_starter",
            "inputs": inputs,
        }
        return (
            security_plan_text_ec2_starter(
                inputs["instance_name"],
                inputs["region"],
                inputs["instance_type"],
                inputs["assign_public_ip"],
            ),
            PendingPlanItem(plan_id=plan_id, plan_type="ec2"),
        )

    return None


@router.post("/confirm-action", response_model=ConfirmActionResponse)
async def confirm_action(
    request: ConfirmActionRequest,
    user: Annotated[User, Depends(get_current_user)],
    conn: Annotated[AwsConnection, Depends(get_active_aws_connection)],
):
    ws = workspace_for_user(user.id)

    pending = ws.setdefault("pending_actions", {})
    action = pending.get(request.action_id)
    if not action:
        raise HTTPException(
            status_code=404,
            detail="No pending action with that id. It may have expired or already run.",
        )

    service = action["service"]
    operation = action["operation"]
    params = action.get("params") or {}
    if not needs_user_confirmation(service, operation):
        raise HTTPException(
            status_code=400,
            detail="This action does not require confirmation.",
        )
    allowed_ops = ALLOWED_AWS_ACTIONS.get(service)
    if allowed_ops is None or operation not in allowed_ops:
        raise HTTPException(status_code=400, detail="Action is no longer allowed.")
    if not isinstance(params, dict):
        raise HTTPException(status_code=400, detail="Invalid stored action parameters.")

    exec_entry = get_execution_entry(user.id, conn)
    pending.pop(request.action_id, None)
    results = execute_aws_actions(
        exec_entry,
        [{"service": service, "operation": operation, "params": params}],
    )
    if not results:
        raise HTTPException(status_code=500, detail="No result from executor.")
    r = results[0]
    if not r.get("ok"):
        pending[request.action_id] = action
    return ConfirmActionResponse(result=ActionResultItem(**r))


@router.post("/chat", response_model=ChatResponse)
async def chat_with_gemini(
    request: ChatRequest,
    user: Annotated[User, Depends(get_current_user)],
    conn: Annotated[AwsConnection, Depends(get_active_aws_connection)],
):
    ws = workspace_for_user(user.id)

    try:
        exec_entry = get_execution_entry(user.id, conn)
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail="Could not refresh AWS session. Reconnect in the app.",
        ) from e

    account_id = exec_entry.get("account_id") or conn.aws_account_id or ""
    region = conn.region or exec_entry.get("region", "us-east-1")

    try:
        starter_plan = _starter_plan_from_chat(request.prompt, region, ws)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if starter_plan:
        reply, pending_plan = starter_plan
        return ChatResponse(
            reply=reply,
            action_results=[],
            pending_actions=[],
            pending_plan=pending_plan,
        )

    full_prompt = build_chat_full_prompt(account_id, region, request.prompt)

    try:
        raw_text = generate_model_reply(full_prompt)
    except Exception as e:
        print(f"Error calling Gemini: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while generating response.",
        ) from e

    explanation, actions = parse_chat_response_text(raw_text)
    ws.setdefault("pending_actions", {})

    to_execute, pending_items = partition_actions_for_chat(ws, actions)
    action_results = execute_aws_actions(exec_entry, to_execute)

    if pending_items:
        explanation = (explanation or "").rstrip()
        explanation += (
            "\n\nAction required: review and confirm the pending change below "
            "before it runs in AWS."
        )

    return ChatResponse(
        reply=explanation,
        action_results=[ActionResultItem(**r) for r in action_results],
        pending_actions=pending_items,
    )
