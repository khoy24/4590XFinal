import ipaddress
import json
import re
import uuid
import urllib.parse
from typing import Any

import boto3
import google.generativeai as genai
import os
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# load environment variables from .env file
load_dotenv()

# configure Gemini API
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    raise ValueError("GEMINI_API_KEY is missing from the .env file")

genai.configure(api_key=gemini_api_key)
model = genai.GenerativeModel("gemini-2.5-flash")

# get account id from backend .env
BACKEND_ACCOUNT_ID = os.getenv("AWS_BACKEND_ACCOUNT_ID")
if not BACKEND_ACCOUNT_ID:
    print("WARNING: AWS_BACKEND_ACCOUNT_ID is missing from .env. The link will not work.")

app = FastAPI(title="Cloud Deployment Assistant API")

#  CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# in-memory session store
sessions: dict[str, dict[str, Any]] = {}

# only these can be used
ALLOWED_AWS_ACTIONS: dict[str, frozenset[str]] = {
    "s3": frozenset({"list_buckets", "create_bucket"}),
    "ec2": frozenset(
        {
            "describe_instances",
            "describe_security_groups",
            "describe_vpcs",
            "describe_route_tables",
            "create_vpc",
            "modify_vpc_attribute",
            "create_subnet",
            "create_internet_gateway",
            "attach_internet_gateway",
            "create_route_table",
            "create_route",
            "associate_route_table",
            "create_tags",
        }
    ),
    "iam": frozenset({"list_users", "get_user"}),
    "sts": frozenset({"get_caller_identity"}),
}

# (service, operation) pairs that require explicit user confirmation before execution
CONFIRMATION_REQUIRED_OPS: frozenset[tuple[str, str]] = frozenset(
    {
        ("s3", "create_bucket"),
        ("ec2", "create_vpc"),
        ("ec2", "modify_vpc_attribute"),
        ("ec2", "create_subnet"),
        ("ec2", "create_internet_gateway"),
        ("ec2", "attach_internet_gateway"),
        ("ec2", "create_route_table"),
        ("ec2", "create_route"),
        ("ec2", "associate_route_table"),
        ("ec2", "create_tags"),
    }
)


def _needs_user_confirmation(service: str, operation: str) -> bool:
    return (service, operation) in CONFIRMATION_REQUIRED_OPS


def _validate_allowlisted_action(
    raw: dict[str, Any],
) -> tuple[bool, str, str, dict[str, Any]]:
    """Return (is_valid, service, operation, params). Invalid means executor will report error."""
    service = (raw.get("service") or "").strip().lower()
    operation = (raw.get("operation") or "").strip()
    params = raw.get("params") if raw.get("params") is not None else {}
    if not isinstance(params, dict):
        return False, service, operation, {}
    allowed_ops = ALLOWED_AWS_ACTIONS.get(service)
    if allowed_ops is None or operation not in allowed_ops:
        return False, service, operation, params
    return True, service, operation, params


def _risk_summary_for_action(
    service: str, operation: str, params: dict[str, Any]
) -> str:
    if service == "s3" and operation == "create_bucket":
        name = params.get("Bucket", "(unnamed)")
        return (
            f"This will create a new S3 bucket named {name} in your account. "
            "You may incur storage charges if objects are uploaded. "
            "Confirm only if you intend to create this bucket."
        )
    if service == "ec2":
        op_label = operation.replace("_", " ")
        return (
            f"This EC2 API call ({op_label}) changes networking resources in your account. "
            "Confirm only if you intend to proceed."
        )
    return (
        "This action can change resources in your AWS account. "
        "Confirm only if you intend to proceed."
    )


_TAGS_SAFE = re.compile(r"^[A-Za-z0-9 ._:/=+\-@]{1,256}$")


def _sanitize_project_tag(name: str) -> str:
    s = " ".join((name or "").strip().split())
    if not s:
        return "cloud-assistant-vpc"
    if len(s) > 256:
        s = s[:256]
    if not _TAGS_SAFE.fullmatch(s):
        out = []
        for c in s:
            if c.isalnum() or c in " ._:/=+-@":
                out.append(c)
            else:
                out.append("-")
        s = "".join(out)[:256] or "cloud-assistant-vpc"
    return s


def _parse_ipv4_cidr(block: str) -> ipaddress.IPv4Network:
    """Parse CIDR block;raises ValueError if invalid."""
    n = ipaddress.ip_network(block.strip(), strict=False)
    if not isinstance(n, ipaddress.IPv4Network):
        raise ValueError("Only IPv4 CIDR blocks are supported.")
    return n


def _validate_vpc_starter_inputs(
    vpc_cidr: str,
    public_cidr: str,
    private_cidr: str,
) -> dict[str, str]:
    vpc_net = _parse_ipv4_cidr(vpc_cidr)
    pub_net = _parse_ipv4_cidr(public_cidr)
    prv_net = _parse_ipv4_cidr(private_cidr)
    if pub_net.prefixlen == 0 or prv_net.prefixlen == 0:
        raise ValueError("Subnet prefixes must not be default routes.")
    if pub_net.overlaps(prv_net):
        raise ValueError("Public and private subnet CIDR blocks must not overlap.")

    if not pub_net.subnet_of(vpc_net):
        raise ValueError(f"Public subnet {public_cidr} must lie inside VPC {vpc_cidr}.")
    if not prv_net.subnet_of(vpc_net):
        raise ValueError(f"Private subnet {private_cidr} must lie inside VPC {vpc_cidr}.")
    return {
        "vpc_cidr": str(vpc_net),
        "public_subnet_cidr": str(pub_net),
        "private_subnet_cidr": str(prv_net),
    }


def _security_plan_text_vpc_starter(project: str, region: str, cidrs: dict[str, str]) -> str:
    return (
        f"**VPC starter plan ({project}) in {region}**\n\n"
        "What will be created:\n"
        f"- VPC with CIDR `{cidrs['vpc_cidr']}` (DNS hostnames/support enabled).\n"
        "- One **public** subnet and one **private** subnet (AWS picks an Availability Zone).\n"
        "- An Internet Gateway attached to the VPC.\n"
        "- A **public** route table with a route to `0.0.0.0/0` via that gateway, linked to the **public** subnet.\n\n"
        "Security posture:\n"
        "- No security groups are created and **no inbound rules** are opened by this flow.\n"
        "- **Private subnets** have **no** route to the Internet Gateway (starter pattern only; outbound via NAT not included).\n\n"
        "**Confirm only if** you intend to provision these networking resources (may incur trivial charges)."
    )



# classes for gemini chat
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

# classes for guided vpc starter
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


def _boto_session_from_stored(entry: dict[str, Any]) -> boto3.Session:
    """Builds a session using the TEMPORARY credentials from AssumeRole."""
    creds = entry["creds"]
    return boto3.Session(
        aws_access_key_id=creds["access_key"],
        aws_secret_access_key=creds["secret_key"],
        aws_session_token=creds["session_token"], # required for roles
        region_name=entry.get("region", "us-east-1"),
    )


def _parse_gemini_json(text: str) -> dict[str, Any]:
    """Extract JSON object from model output (handles optional markdown fences)."""
    s = text.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", s)
    if fence:
        s = fence.group(1).strip()
    return json.loads(s)


def _partition_actions_for_chat(
    entry: dict[str, Any], actions: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[PendingActionItem]]:
    """Split Gemini actions into those to execute immediately vs pending confirmation."""
    entry.setdefault("pending_actions", {})
    to_execute: list[dict[str, Any]] = []
    pending_items: list[PendingActionItem] = []

    for raw in actions:
        valid, service, operation, params = _validate_allowlisted_action(raw)
        if not valid:
            to_execute.append(raw)
            continue
        normalized = {"service": service, "operation": operation, "params": params}
        if _needs_user_confirmation(service, operation):
            action_id = str(uuid.uuid4())
            entry["pending_actions"][action_id] = {
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
                    risk_summary=_risk_summary_for_action(service, operation, params),
                )
            )
        else:
            to_execute.append(normalized)

    return to_execute, pending_items


@app.get("/generate-aws-link")
async def generate_aws_link(user_id: str):
    """Generates the link and stores the required External ID."""
    if not BACKEND_ACCOUNT_ID:
        raise HTTPException(status_code=500, detail="Backend not configured correctly.")

    unique_external_id = str(uuid.uuid4())
    
    sessions[user_id] = {
        "status": "pending",
        "external_id": unique_external_id
    }
    
    # gist URL / yaml template (change this to a new S3 bucket if you need to change yaml)
    template_url = "https://ryan-cloud-assistant-templates.s3.us-east-1.amazonaws.com/template.yaml"
    encoded_url = urllib.parse.quote(template_url)
    template_link = f"https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/quickcreate?templateURL={encoded_url}&stackName=CloudAssistant&param_ExternalID={unique_external_id}&param_BackendAccountID={BACKEND_ACCOUNT_ID}"
    
    return {"link": template_link}


@app.post("/verify-role")
async def verify_aws_role(request: VerifyRoleRequest):
    """Performs the handshake and stores temporary credentials."""
    session_data = sessions.get(request.session_id)
    
    if not session_data or session_data.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Invalid session. Please reopen the connection modal.")

    sts_client = boto3.client('sts')
    
    try:
        response = sts_client.assume_role(
            RoleArn=request.role_arn,
            RoleSessionName="CloudAssistantSession",
            ExternalId=session_data["external_id"]
        )
        
        credentials = response['Credentials']
        assumed_role_user = response['AssumedRoleUser']
        
        # Update our session store with the active temporary credentials
        sessions[request.session_id] = {
            "status": "active",
            "creds": {
                "access_key": credentials['AccessKeyId'],
                "secret_key": credentials['SecretAccessKey'],
                "session_token": credentials['SessionToken'],
            },
            "account_id": assumed_role_user['Arn'].split(':')[4],
            "user_arn": assumed_role_user['Arn'],
            "region": request.region,
            "pending_actions": {},
            "pending_plans": {},
        }
        
        return {
            "status": "success",
            "message": "Successfully assumed role!",
            "account_id": sessions[request.session_id]["account_id"],
            "user_arn": sessions[request.session_id]["user_arn"],
            "region": sessions[request.session_id]["region"],
        }

    except ClientError as e:
        raise HTTPException(status_code=403, detail=f"Access Denied: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/confirm-action", response_model=ConfirmActionResponse)
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
    if not _needs_user_confirmation(service, operation):
        raise HTTPException(status_code=400, detail="This action does not require confirmation.")
    allowed_ops = ALLOWED_AWS_ACTIONS.get(service)
    if allowed_ops is None or operation not in allowed_ops:
        raise HTTPException(status_code=400, detail="Action is no longer allowed.")
    if not isinstance(params, dict):
        raise HTTPException(status_code=400, detail="Invalid stored action parameters.")

    pending.pop(request.action_id, None)
    results = _execute_aws_actions(
        entry,
        [{"service": service, "operation": operation, "params": params}],
    )
    if not results:
        raise HTTPException(status_code=500, detail="No result from executor.")
    r = results[0]
    if not r.get("ok"):
        pending[request.action_id] = action
    return ConfirmActionResponse(result=ActionResultItem(**r))


@app.post("/plan-vpc-starter", response_model=PlanVpcStarterResponse)
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
        cidrs = _validate_vpc_starter_inputs(
            request.vpc_cidr,
            request.public_subnet_cidr,
            request.private_subnet_cidr,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    project = _sanitize_project_tag(request.project_name)
    inputs: dict[str, str] = {
        "project_name": project,
        "vpc_cidr": cidrs["vpc_cidr"],
        "public_subnet_cidr": cidrs["public_subnet_cidr"],
        "private_subnet_cidr": cidrs["private_subnet_cidr"],
    }
    security_plan = _security_plan_text_vpc_starter(project, session_region, cidrs)
    plan_id = str(uuid.uuid4())
    entry.setdefault("pending_plans", {})[plan_id] = {
        "kind": "vpc_starter",
        "inputs": inputs,
    }
    return PlanVpcStarterResponse(plan_id=plan_id, security_plan=security_plan)


@app.post("/confirm-plan", response_model=ConfirmPlanResponse)
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

    raw_results = _run_vpc_starter_plan(entry, inputs)
    return ConfirmPlanResponse(results=[ActionResultItem(**r) for r in raw_results])


def _execute_aws_actions(
    entry: dict[str, Any], actions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Run allowlisted boto3 calls; return one result dict per action."""
    results: list[dict[str, Any]] = []
    boto_sess = _boto_session_from_stored(entry)
    for raw in actions:
        service = (raw.get("service") or "").strip().lower()
        operation = (raw.get("operation") or "").strip()
        params = raw.get("params") or {}
        if not isinstance(params, dict):
            results.append(
                {
                    "service": service,
                    "operation": operation,
                    "ok": False,
                    "error": "params must be an object",
                }
            )
            continue
        allowed_ops = ALLOWED_AWS_ACTIONS.get(service)
        if allowed_ops is None or operation not in allowed_ops:
            results.append(
                {
                    "service": service,
                    "operation": operation,
                    "ok": False,
                    "error": "Operation not allowed or unknown service",
                }
            )
            continue
        try:
            client = boto_sess.client(service)
            method = getattr(client, operation)
            out = method(**params)
            # Drop non-JSON-serializable / huge payload noise for common read calls
            summary = _summarize_response(service, operation, out)
            results.append(
                {
                    "service": service,
                    "operation": operation,
                    "ok": True,
                    "result": summary,
                }
            )
        except ClientError as e:
            results.append(
                {
                    "service": service,
                    "operation": operation,
                    "ok": False,
                    "error": e.response.get("Error", {}).get("Message", str(e)),
                }
            )
        except Exception as e:
            results.append(
                {
                    "service": service,
                    "operation": operation,
                    "ok": False,
                    "error": str(e),
                }
            )
    return results


def _summarize_response(service: str, operation: str, out: dict[str, Any]) -> Any:
    """Shrink boto3 responses for API/JSON and chat display."""
    if service == "s3" and operation == "list_buckets":
        buckets = out.get("Buckets") or []
        return {
            "bucket_count": len(buckets),
            "names": [b.get("Name") for b in buckets[:20]],
        }
    if service == "s3" and operation == "create_bucket":
        return {"Location": out.get("Location"), "Bucket": out.get("Bucket")}
    if service == "ec2" and operation == "describe_instances":
        reservations = out.get("Reservations") or []
        count = sum(len(r.get("Instances") or []) for r in reservations)
        return {"reservation_count": len(reservations), "instance_count": count}
    if service == "ec2" and operation == "describe_security_groups":
        sgs = out.get("SecurityGroups") or []
        return {
            "count": len(sgs),
            "group_ids": [g.get("GroupId") for g in sgs[:15]],
        }
    if service == "ec2" and operation == "describe_vpcs":
        vpcs = out.get("Vpcs") or []
        return {"count": len(vpcs), "vpc_ids": [v.get("VpcId") for v in vpcs[:15]]}
    if service == "ec2" and operation == "describe_route_tables":
        rts = out.get("RouteTables") or []
        return {
            "count": len(rts),
            "route_table_ids": [r.get("RouteTableId") for r in rts[:15]],
        }
    if service == "ec2" and operation == "create_vpc":
        vpc = out.get("Vpc") or {}
        return {
            "VpcId": vpc.get("VpcId"),
            "CidrBlock": vpc.get("CidrBlock"),
            "State": vpc.get("State"),
        }
    if service == "ec2" and operation == "modify_vpc_attribute":
        return {"updated": True}
    if service == "ec2" and operation == "create_subnet":
        sn = out.get("Subnet") or {}
        return {
            "SubnetId": sn.get("SubnetId"),
            "VpcId": sn.get("VpcId"),
            "CidrBlock": sn.get("CidrBlock"),
            "AvailabilityZone": sn.get("AvailabilityZone"),
        }
    if service == "ec2" and operation == "create_internet_gateway":
        igw = out.get("InternetGateway") or {}
        return {"InternetGatewayId": igw.get("InternetGatewayId")}
    if service == "ec2" and operation == "attach_internet_gateway":
        return {
            "attached": True,
            "VpcId": out.get("VpcId"),
            "InternetGatewayId": out.get("InternetGatewayId"),
        }
    if service == "ec2" and operation == "create_route_table":
        rt = out.get("RouteTable") or {}
        return {"RouteTableId": rt.get("RouteTableId"), "VpcId": rt.get("VpcId")}
    if service == "ec2" and operation == "create_route":
        rte = out.get("Route") or {}
        return {
            "Return": out.get("Return"),
            "RouteTableId": out.get("RouteTableId"),
            "DestinationCidrBlock": rte.get("DestinationCidrBlock"),
        }
    if service == "ec2" and operation == "associate_route_table":
        return {
            "AssociationId": out.get("AssociationId"),
            "RouteTableId": out.get("RouteTableId"),
            "SubnetId": out.get("SubnetId"),
        }
    if service == "ec2" and operation == "create_tags":
        return {"tagged": True}
    if service == "iam" and operation == "list_users":
        users = out.get("Users") or []
        return {
            "count": len(users),
            "user_names": [u.get("UserName") for u in users[:20]],
        }
    if service == "iam" and operation == "get_user":
        u = out.get("User") or {}
        return {"UserName": u.get("UserName"), "UserId": u.get("UserId")}
    if service == "sts" and operation == "get_caller_identity":
        return {
            "Account": out.get("Account"),
            "Arn": out.get("Arn"),
            "UserId": out.get("UserId"),
        }
    return out


def _one_result(
    service: str,
    operation: str,
    ok: bool,
    result: Any = None,
    error: str | None = None,
) -> dict[str, Any]:
    r: dict[str, Any] = {"service": service, "operation": operation, "ok": ok}
    if result is not None:
        r["result"] = result
    if error is not None:
        r["error"] = error
    return r


def _run_vpc_starter_plan(entry: dict[str, Any], inputs: dict[str, str]) -> list[dict[str, Any]]:
    """Execute VPC starter workflow in order after user confirmation."""
    boto_sess = _boto_session_from_stored(entry)
    ec2 = boto_sess.client("ec2")
    results: list[dict[str, Any]] = []
    project = inputs["project_name"]
    vpc_cidr = inputs["vpc_cidr"]
    pub_cidr = inputs["public_subnet_cidr"]
    prv_cidr = inputs["private_subnet_cidr"]
    vpc_id: str | None = None
    igw_id: str | None = None
    pub_subnet_id: str | None = None
    prv_subnet_id: str | None = None
    rt_id: str | None = None

    def exec_op(op_name: str, fn: Any) -> bool:
        nonlocal vpc_id, igw_id, pub_subnet_id, prv_subnet_id, rt_id
        try:
            raw = fn()
            out = raw if isinstance(raw, dict) else {}
            summary = _summarize_response("ec2", op_name, out)
            results.append(_one_result("ec2", op_name, True, result=summary))
            return True
        except ClientError as e:
            msg = e.response.get("Error", {}).get("Message", str(e))
            results.append(_one_result("ec2", op_name, False, error=msg))
            return False
        except Exception as e:
            results.append(_one_result("ec2", op_name, False, error=str(e)))
            return False

    def step_create_vpc():
        nonlocal vpc_id
        r = ec2.create_vpc(CidrBlock=vpc_cidr)
        vpc_id = r["Vpc"]["VpcId"]
        return r

    if not exec_op("create_vpc", step_create_vpc):
        return results

    def mod_dns_hosts():
        return ec2.modify_vpc_attribute(
            VpcId=vpc_id, EnableDnsHostnames={"Value": True}
        )

    if not exec_op("modify_vpc_attribute", mod_dns_hosts):
        return results

    def mod_dns_support():
        return ec2.modify_vpc_attribute(
            VpcId=vpc_id, EnableDnsSupport={"Value": True}
        )

    if not exec_op("modify_vpc_attribute", mod_dns_support):
        return results

    def tag_vpc():
        return ec2.create_tags(
            Resources=[vpc_id],
            Tags=[
                {"Key": "Name", "Value": project},
                {"Key": "Project", "Value": project},
            ],
        )

    if not exec_op("create_tags", tag_vpc):
        return results

    def step_igw():
        nonlocal igw_id
        r = ec2.create_internet_gateway()
        igw_id = r["InternetGateway"]["InternetGatewayId"]
        return r

    if not exec_op("create_internet_gateway", step_igw):
        return results

    def step_attach():
        return ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)

    if not exec_op("attach_internet_gateway", step_attach):
        return results

    def tag_igw():
        return ec2.create_tags(
            Resources=[igw_id],
            Tags=[
                {"Key": "Name", "Value": f"{project}-igw"},
                {"Key": "Project", "Value": project},
            ],
        )

    if not exec_op("create_tags", tag_igw):
        return results

    def step_pub_subnet():
        nonlocal pub_subnet_id
        r = ec2.create_subnet(VpcId=vpc_id, CidrBlock=pub_cidr)
        pub_subnet_id = r["Subnet"]["SubnetId"]
        return r

    if not exec_op("create_subnet", step_pub_subnet):
        return results

    def step_prv_subnet():
        nonlocal prv_subnet_id
        r = ec2.create_subnet(VpcId=vpc_id, CidrBlock=prv_cidr)
        prv_subnet_id = r["Subnet"]["SubnetId"]
        return r

    if not exec_op("create_subnet", step_prv_subnet):
        return results

    def tag_public_name():
        return ec2.create_tags(
            Resources=[pub_subnet_id],
            Tags=[{"Key": "Name", "Value": f"{project}-public"}],
        )

    def tag_private_name():
        return ec2.create_tags(
            Resources=[prv_subnet_id],
            Tags=[{"Key": "Name", "Value": f"{project}-private"}],
        )

    if not exec_op("create_tags", tag_public_name):
        return results
    if not exec_op("create_tags", tag_private_name):
        return results

    def step_rt():
        nonlocal rt_id
        r = ec2.create_route_table(VpcId=vpc_id)
        rt_id = r["RouteTable"]["RouteTableId"]
        return r

    if not exec_op("create_route_table", step_rt):
        return results

    def step_route():
        return ec2.create_route(
            RouteTableId=rt_id,
            DestinationCidrBlock="0.0.0.0/0",
            GatewayId=igw_id,
        )

    if not exec_op("create_route", step_route):
        return results

    def step_assoc():
        return ec2.associate_route_table(
            RouteTableId=rt_id, SubnetId=pub_subnet_id
        )

    if not exec_op("associate_route_table", step_assoc):
        return results

    def tag_rt():
        return ec2.create_tags(
            Resources=[rt_id],
            Tags=[
                {"Key": "Name", "Value": f"{project}-public-rt"},
                {"Key": "Project", "Value": project},
            ],
        )

    exec_op("create_tags", tag_rt)

    results.append(
        _one_result(
            "vpc_starter",
            "summary",
            True,
            result={
                "VpcId": vpc_id,
                "InternetGatewayId": igw_id,
                "PublicSubnetId": pub_subnet_id,
                "PrivateSubnetId": prv_subnet_id,
                "PublicRouteTableId": rt_id,
            },
        )
    )
    return results


@app.post("/chat", response_model=ChatResponse)
async def chat_with_gemini(request: ChatRequest):
    entry = sessions.get(request.session_id)
    if not entry or entry.get("status") != "active":
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please connect your AWS account.")

    account_id = entry.get("account_id", "")
    user_arn = entry.get("user_arn", "")
    region = entry.get("region", "us-east-1")

    allowed_block = "\n".join(
        f"- {svc}: {', '.join(sorted(ops))}"
        for svc, ops in sorted(ALLOWED_AWS_ACTIONS.items())
    )

    system_prompt = f"""You are a Cloud Security Architect helping a non-technical user work with AWS safely.
The user is connected to AWS account {account_id} in region {region}. Their IAM principal ARN: {user_arn}.

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

    full_prompt = f"{system_prompt}\n\nUser request: {request.prompt}"

    try:
        response = model.generate_content(full_prompt)
        raw_text = (response.text or "").strip()
    except Exception as e:
        print(f"Error calling Gemini: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error while generating response.") from e

    explanation = raw_text
    actions: list[dict[str, Any]] = []
    try:
        parsed = _parse_gemini_json(raw_text)
        explanation = parsed.get("explanation") or raw_text
        raw_actions = parsed.get("aws_actions")
        if isinstance(raw_actions, list):
            actions = [a for a in raw_actions if isinstance(a, dict)]
    except (json.JSONDecodeError, ValueError, TypeError):
        actions = []

    entry.setdefault("pending_actions", {})
    to_execute, pending_items = _partition_actions_for_chat(entry, actions)
    action_results = _execute_aws_actions(entry, to_execute)

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