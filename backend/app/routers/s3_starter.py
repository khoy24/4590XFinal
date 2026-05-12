import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_active_aws_connection, get_current_user
from app.models import AwsConnection, User
from app.schemas import (
    ActionResultItem,
    ConfirmS3PlanRequest,
    ConfirmS3PlanResponse,
    PlanS3StarterRequest,
    PlanS3StarterResponse,
)
from app.services.credential_manager import get_execution_entry
from app.services.s3_starter import (
    run_s3_starter_plan,
    sanitize_bucket_name,
    security_plan_text_s3_starter,
    validate_s3_starter_inputs,
)
from app.state import workspace_for_user

router = APIRouter()


@router.post("/plan-s3-starter", response_model=PlanS3StarterResponse)
async def plan_s3_starter(
    request: PlanS3StarterRequest,
    user: Annotated[User, Depends(get_current_user)],
    conn: Annotated[AwsConnection, Depends(get_active_aws_connection)],
):
    exec_entry = get_execution_entry(user.id, conn)

    session_region = conn.region or exec_entry.get("region") or "us-east-1"
    if request.region and request.region.strip() != str(session_region).strip():
        raise HTTPException(
            status_code=400,
            detail=f"Region must match the connected session ({session_region}). Change the connection region or omit region.",
        )
    try:
        validated = validate_s3_starter_inputs(
            request.bucket_name,
            session_region,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    bucket = sanitize_bucket_name(request.bucket_name)
    inputs: dict[str, Any] = {
        "bucket_name": bucket,
        "region": session_region,
        "enable_encryption": request.enable_encryption,
        "enable_versioning": request.enable_versioning,
        "block_public_access": request.block_public_access,
    }
    security_plan = security_plan_text_s3_starter(
        bucket, session_region, request.enable_encryption, request.enable_versioning, request.block_public_access
    )
    plan_id = str(uuid.uuid4())
    ws = workspace_for_user(user.id)
    ws.setdefault("pending_plans", {})[plan_id] = {
        "kind": "s3_starter",
        "inputs": inputs,
    }
    return PlanS3StarterResponse(plan_id=plan_id, security_plan=security_plan)


@router.post("/confirm-s3-plan", response_model=ConfirmS3PlanResponse)
async def confirm_s3_plan(
    request: ConfirmS3PlanRequest,
    user: Annotated[User, Depends(get_current_user)],
    conn: Annotated[AwsConnection, Depends(get_active_aws_connection)],
):
    exec_entry = get_execution_entry(user.id, conn)

    ws = workspace_for_user(user.id)
    plans = ws.setdefault("pending_plans", {})
    plan = plans.pop(request.plan_id, None)
    if not plan:
        raise HTTPException(
            status_code=404,
            detail="No pending plan with that id. It may have expired or already ran.",
        )
    if plan.get("kind") != "s3_starter":
        raise HTTPException(status_code=400, detail="Unknown plan type.")
    inputs = plan.get("inputs") or {}
    if not isinstance(inputs, dict):
        raise HTTPException(status_code=400, detail="Invalid stored plan inputs.")

    raw_results = run_s3_starter_plan(exec_entry, inputs)
    return ConfirmS3PlanResponse(
        results=[ActionResultItem(**r) for r in raw_results]
    )