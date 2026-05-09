import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_active_aws_connection, get_current_user
from app.models import AwsConnection, User
from app.schemas import (
    ActionResultItem,
    ConfirmEc2PlanRequest,
    ConfirmEc2PlanResponse,
    PlanEc2StarterRequest,
    PlanEc2StarterResponse,
)
from app.services.credential_manager import get_execution_entry
from app.services.ec2_starter import (
    run_ec2_starter_plan,
    security_plan_text_ec2_starter,
    validate_ec2_starter_inputs,
)
from app.state import workspace_for_user

router = APIRouter()


@router.post("/plan-ec2-starter", response_model=PlanEc2StarterResponse)
async def plan_ec2_starter(
    request: PlanEc2StarterRequest,
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
        validated = validate_ec2_starter_inputs(
            request.instance_name,
            request.instance_type,
            request.assign_public_ip,
            session_region,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    inputs = {
        "instance_name": validated["instance_name"],
        "region": validated["region"],
        "instance_type": validated["instance_type"],
        "assign_public_ip": validated["assign_public_ip"],
    }
    security_plan = security_plan_text_ec2_starter(
        inputs["instance_name"],
        inputs["region"],
        inputs["instance_type"],
        inputs["assign_public_ip"],
    )
    plan_id = str(uuid.uuid4())
    ws = workspace_for_user(user.id)
    ws.setdefault("pending_plans", {})[plan_id] = {
        "kind": "ec2_starter",
        "inputs": inputs,
    }
    return PlanEc2StarterResponse(plan_id=plan_id, security_plan=security_plan)


@router.post("/confirm-ec2-plan", response_model=ConfirmEc2PlanResponse)
async def confirm_ec2_plan(
    request: ConfirmEc2PlanRequest,
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
    if plan.get("kind") != "ec2_starter":
        raise HTTPException(status_code=400, detail="Unknown plan type.")
    inputs = plan.get("inputs") or {}
    if not isinstance(inputs, dict):
        raise HTTPException(status_code=400, detail="Invalid stored plan inputs.")

    raw_results = run_ec2_starter_plan(exec_entry, inputs)
    return ConfirmEc2PlanResponse(
        results=[ActionResultItem(**r) for r in raw_results]
    )
