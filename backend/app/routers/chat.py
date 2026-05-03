from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from app.deps import get_active_aws_connection, get_current_user
from app.models import AwsConnection, User
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
from app.services.credential_manager import get_execution_entry
from app.services.gemini import (
    build_chat_full_prompt,
    generate_model_reply,
    parse_chat_response_text,
    partition_actions_for_chat,
)
from app.state import workspace_for_user

router = APIRouter()


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
