# /backend/main.py
import json
import re
import uuid
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

# right now use gemini-2.5-flash as it is fast and cheap
model = genai.GenerativeModel("gemini-2.5-flash")

# initialize FastAPI App
app = FastAPI(title="Cloud Deployment Assistant API")

# setup CORS (Cross-Origin Resource Sharing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store: session_id -> creds + AWS identity (never persisted to disk)
sessions: dict[str, dict[str, Any]] = {}

# Only these (service, operation) pairs may be executed (boto3 client method names)
ALLOWED_AWS_ACTIONS: dict[str, frozenset[str]] = {
    "s3": frozenset({"list_buckets", "create_bucket"}),
    "ec2": frozenset(
        {"describe_instances", "describe_security_groups", "describe_vpcs"}
    ),
    "iam": frozenset({"list_users", "get_user"}),
    "sts": frozenset({"get_caller_identity"}),
}


def _boto_session_from_stored(entry: dict[str, Any]) -> boto3.Session:
    creds = entry["creds"]
    return boto3.Session(
        aws_access_key_id=creds["access_key"],
        aws_secret_access_key=creds["secret_key"],
        aws_session_token=creds.get("session_token") or None,
        region_name=creds["region"],
    )


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


class ConnectRequest(BaseModel):
    access_key: str = Field(..., min_length=16)
    secret_key: str = Field(..., min_length=1)
    session_token: str | None = None
    region: str = Field(..., min_length=1)


class ConnectResponse(BaseModel):
    session_id: str
    account_id: str
    user_arn: str
    region: str


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


@app.post("/connect", response_model=ConnectResponse)
async def connect_aws(request: ConnectRequest):
    """Validate credentials via STS; store in memory only."""
    session_kw: dict[str, Any] = {
        "aws_access_key_id": request.access_key,
        "aws_secret_access_key": request.secret_key,
        "region_name": request.region,
    }
    if request.session_token:
        session_kw["aws_session_token"] = request.session_token
    try:
        sts = boto3.client("sts", **session_kw)
        ident = sts.get_caller_identity()
    except ClientError as e:
        raise HTTPException(
            status_code=401,
            detail=e.response.get("Error", {}).get("Message", "Invalid credentials"),
        ) from e
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    account_id = ident.get("Account") or ""
    user_arn = ident.get("Arn") or ""
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "creds": {
            "access_key": request.access_key,
            "secret_key": request.secret_key,
            "session_token": request.session_token,
            "region": request.region,
        },
        "account_id": account_id,
        "user_arn": user_arn,
    }
    return ConnectResponse(
        session_id=session_id,
        account_id=account_id,
        user_arn=user_arn,
        region=request.region,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat_with_gemini(request: ChatRequest):
    entry = sessions.get(request.session_id)
    if not entry:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    account_id = entry.get("account_id", "")
    user_arn = entry.get("user_arn", "")
    region = entry["creds"]["region"]

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
        raise HTTPException(
            status_code=500,
            detail="Internal Server Error while generating response.",
        ) from e

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


@app.get("/")
async def health_check():
    return {"status": "Backend is running!"}
