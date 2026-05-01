from fastapi import APIRouter, HTTPException

from app.schemas import (
    ActionResultItem,
    ChatRequest,
    ChatResponse,
    ConfirmActionRequest,
    ConfirmActionResponse,
)
from app.services.aws_actions import (
    ALLOWED_AWS_ACTIONS,
    execute_aws_actions,
    needs_user_confirmation,
)
from app.services.gemini import (
    build_chat_full_prompt,
    generate_model_reply,
    parse_chat_response_text,
    partition_actions_for_chat,
)
from app.state import sessions

router = APIRouter()


@router.post("/confirm-action", response_model=ConfirmActionResponse)
async def confirm_action(request: ConfirmActionRequest):
    """Execute a previously staged write action after explicit user confirmation."""
    entry = sessions.get(request.session_id)
    if not entry or entry.get("status") != "active":
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session. Please connect your AWS account.",
        )

    pending = entry.setdefault("pending_actions", {})
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

    pending.pop(request.action_id, None)
    results = execute_aws_actions(
        entry,
        [{"service": service, "operation": operation, "params": params}],
    )
    if not results:
        raise HTTPException(status_code=500, detail="No result from executor.")
    r = results[0]
    if not r.get("ok"):
        pending[request.action_id] = action
    return ConfirmActionResponse(result=ActionResultItem(**r))


@router.post("/chat", response_model=ChatResponse)
async def chat_with_gemini(request: ChatRequest):
    entry = sessions.get(request.session_id)
    if not entry or entry.get("status") != "active":
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session. Please connect your AWS account.",
        )

    account_id = entry.get("account_id", "")
    user_arn = entry.get("user_arn", "")
    region = entry.get("region", "us-east-1")

    full_prompt = build_chat_full_prompt(
        account_id, user_arn, region, request.prompt
    )

    try:
        raw_text = generate_model_reply(full_prompt)
    except Exception as e:
        print(f"Error calling Gemini: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while generating response.",
        ) from e

    explanation, actions = parse_chat_response_text(raw_text)

    entry.setdefault("pending_actions", {})
    to_execute, pending_items = partition_actions_for_chat(entry, actions)
    action_results = execute_aws_actions(entry, to_execute)

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
