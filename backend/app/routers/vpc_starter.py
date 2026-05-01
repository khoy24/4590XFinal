import uuid

from fastapi import APIRouter, HTTPException

from app.schemas import (
    ActionResultItem,
    ConfirmPlanRequest,
    ConfirmPlanResponse,
    PlanVpcStarterRequest,
    PlanVpcStarterResponse,
)
from app.services.vpc_starter import (
    run_vpc_starter_plan,
    sanitize_project_tag,
    security_plan_text_vpc_starter,
    validate_vpc_starter_inputs,
)
from app.state import sessions

router = APIRouter()


@router.post("/plan-vpc-starter", response_model=PlanVpcStarterResponse)
async def plan_vpc_starter(request: PlanVpcStarterRequest):
    """Stage a guided VPC starter deployment for explicit user confirmation."""
    entry = sessions.get(request.session_id)
    if not entry or entry.get("status") != "active":
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session. Please connect your AWS account.",
        )
    session_region = entry.get("region") or "us-east-1"
    if request.region and request.region.strip() != str(session_region).strip():
        raise HTTPException(
            status_code=400,
            detail=f"Region must match the connected session ({session_region}). Change the connection region or omit region.",
        )
    try:
        cidrs = validate_vpc_starter_inputs(
            request.vpc_cidr,
            request.public_subnet_cidr,
            request.private_subnet_cidr,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    project = sanitize_project_tag(request.project_name)
    inputs: dict[str, str] = {
        "project_name": project,
        "vpc_cidr": cidrs["vpc_cidr"],
        "public_subnet_cidr": cidrs["public_subnet_cidr"],
        "private_subnet_cidr": cidrs["private_subnet_cidr"],
    }
    security_plan = security_plan_text_vpc_starter(project, session_region, cidrs)
    plan_id = str(uuid.uuid4())
    entry.setdefault("pending_plans", {})[plan_id] = {
        "kind": "vpc_starter",
        "inputs": inputs,
    }
    return PlanVpcStarterResponse(plan_id=plan_id, security_plan=security_plan)


@router.post("/confirm-plan", response_model=ConfirmPlanResponse)
async def confirm_plan(request: ConfirmPlanRequest):
    """Execute a staged guided plan after user confirmation."""
    entry = sessions.get(request.session_id)
    if not entry or entry.get("status") != "active":
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session. Please connect your AWS account.",
        )
    plans = entry.setdefault("pending_plans", {})
    plan = plans.pop(request.plan_id, None)
    if not plan:
        raise HTTPException(
            status_code=404,
            detail="No pending plan with that id. It may have expired or already ran.",
        )
    if plan.get("kind") != "vpc_starter":
        raise HTTPException(status_code=400, detail="Unknown plan type.")
    inputs = plan.get("inputs") or {}
    if not isinstance(inputs, dict):
        raise HTTPException(status_code=400, detail="Invalid stored plan inputs.")

    raw_results = run_vpc_starter_plan(entry, inputs)
    return ConfirmPlanResponse(
        results=[ActionResultItem(**r) for r in raw_results]
    )
