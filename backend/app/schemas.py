from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    prompt: str
    session_id: str


class ActionResultItem(BaseModel):
    service: str
    operation: str
    ok: bool
    result: Any | None = None
    error: str | None = None


class PendingActionItem(BaseModel):
    action_id: str
    service: str
    operation: str
    params: dict[str, Any] = {}
    risk_summary: str


class ChatResponse(BaseModel):
    reply: str
    action_results: list[ActionResultItem] = []
    pending_actions: list[PendingActionItem] = []


class VerifyRoleRequest(BaseModel):
    session_id: str
    role_arn: str
    region: str = "us-east-1"


class ConfirmActionRequest(BaseModel):
    session_id: str
    action_id: str


class ConfirmActionResponse(BaseModel):
    result: ActionResultItem


class PlanVpcStarterRequest(BaseModel):
    session_id: str
    project_name: str
    region: str | None = None
    vpc_cidr: str = "10.0.0.0/16"
    public_subnet_cidr: str = "10.0.1.0/24"
    private_subnet_cidr: str = "10.0.2.0/24"


class PlanVpcStarterResponse(BaseModel):
    plan_id: str
    security_plan: str


class ConfirmPlanRequest(BaseModel):
    session_id: str
    plan_id: str


class ConfirmPlanResponse(BaseModel):
    results: list[ActionResultItem]
