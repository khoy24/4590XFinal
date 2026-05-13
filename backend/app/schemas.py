from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    prompt: str


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


class PendingPlanItem(BaseModel):
    plan_id: str
    plan_type: str
    status: str = "open"


class ChatResponse(BaseModel):
    reply: str
    action_results: list[ActionResultItem] = []
    pending_actions: list[PendingActionItem] = []
    pending_plan: PendingPlanItem | None = None


class VerifyRoleRequest(BaseModel):
    region: str = "us-east-1"


class ConfirmActionRequest(BaseModel):
    action_id: str


class ConfirmActionResponse(BaseModel):
    result: ActionResultItem


class PlanVpcStarterRequest(BaseModel):
    project_name: str
    region: str | None = None
    vpc_cidr: str = "10.0.0.0/16"
    public_subnet_cidr: str = "10.0.1.0/24"
    private_subnet_cidr: str = "10.0.2.0/24"


class PlanVpcStarterResponse(BaseModel):
    plan_id: str
    security_plan: str


class ConfirmPlanRequest(BaseModel):
    plan_id: str


class ConfirmPlanResponse(BaseModel):
    results: list[ActionResultItem]


class PlanS3StarterRequest(BaseModel):
    bucket_name: str
    region: str | None = None
    enable_encryption: bool = True
    enable_versioning: bool = False
    block_public_access: bool = True


class PlanS3StarterResponse(BaseModel):
    plan_id: str
    security_plan: str


class ConfirmS3PlanRequest(BaseModel):
    plan_id: str


class ConfirmS3PlanResponse(BaseModel):
    results: list[ActionResultItem]


class PlanEc2StarterRequest(BaseModel):
    instance_name: str
    region: str | None = None
    instance_type: str = "t3.micro"
    assign_public_ip: bool = False


class PlanEc2StarterResponse(BaseModel):
    plan_id: str
    security_plan: str


class ConfirmEc2PlanRequest(BaseModel):
    plan_id: str


class ConfirmEc2PlanResponse(BaseModel):
    results: list[ActionResultItem]


# payload for webhook
class WebhookPayload(BaseModel):
    external_id: str
    role_arn: str
