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
from pydantic import BaseModel, Field

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
    "ec2": frozenset({"describe_instances", "describe_security_groups", "describe_vpcs"}),
    "iam": frozenset({"list_users", "get_user"}),
    "sts": frozenset({"get_caller_identity"}),
}

# classes for the gemini chat
class ChatRequest(BaseModel):
    prompt: str
    session_id: str

class ActionResultItem(BaseModel):
    service: str
    operation: str
    ok: bool
    result: Any | None = None
    error: str | None = None

class ChatResponse(BaseModel):
    reply: str
    action_results: list[ActionResultItem] = []

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

class VerifyRoleRequest(BaseModel):
    session_id: str
    role_arn: str
    region: str = "us-east-1"

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
    
    # gist URL / yaml template
    template_url = "https://cloud-assistant-template-1.s3.us-east-1.amazonaws.com/template.yaml"
    encoded_url = urllib.parse.quote(template_url)
    magic_link = f"https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/quickcreate?templateURL={encoded_url}&stackName=CloudAssistant&param_ExternalID={unique_external_id}&param_BackendAccountID={BACKEND_ACCOUNT_ID}"
    
    return {"link": magic_link}


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
            "region": request.region
        }
        
        return {"status": "success", "message": "Successfully assumed role!"}
        
    except ClientError as e:
        raise HTTPException(status_code=403, detail=f"Access Denied: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _parse_gemini_json(text: str) -> dict[str, Any]:
    """Extract JSON object from model output (handles optional markdown fences)."""
    s = text.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", s)
    if fence:
        s = fence.group(1).strip()
    return json.loads(s)


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

    action_results = _execute_aws_actions(entry, actions)
    return ChatResponse(
        reply=explanation,
        action_results=[ActionResultItem(**r) for r in action_results],
    )