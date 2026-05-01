import uuid
import urllib.parse
import os

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException

from app.config import BACKEND_ACCOUNT_ID
from app.schemas import VerifyRoleRequest, WebhookPayload
from app.state import sessions

router = APIRouter()

# get ngrok URL
WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN")

@router.get("/generate-aws-link")
async def generate_aws_link(user_id: str):
    if not BACKEND_ACCOUNT_ID:
        raise HTTPException(status_code=500, detail="Backend not configured correctly.")

    unique_external_id = str(uuid.uuid4())

    sessions[user_id] = {
        "status": "pending",
        "external_id": unique_external_id,
        "role_arn": None
    }

    template_url = "https://cloud-assistant-template-1.s3.us-east-1.amazonaws.com/template.yaml"
    encoded_url = urllib.parse.quote(template_url)
    
    # now must append the webhook URL
    webhook_url = f"{WEBHOOK_DOMAIN}/aws-webhook"
    encoded_webhook = urllib.parse.quote(webhook_url)

    template_link = f"https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/quickcreate?templateURL={encoded_url}&stackName=CloudAssistant&param_ExternalID={unique_external_id}&param_BackendAccountID={BACKEND_ACCOUNT_ID}&param_WebhookURL={encoded_webhook}"

    return {"link": template_link}

# webhook post function so users don't have to copy & paste the ARN
@router.post("/aws-webhook")
async def receive_aws_webhook(payload: WebhookPayload):
    """Receives the ARN silently from AWS Lambda"""
    target_session_id = None
    for session_id, data in sessions.items():
        if data.get("external_id") == payload.external_id:
            target_session_id = session_id
            break

    if target_session_id:
        sessions[target_session_id]["role_arn"] = payload.role_arn
        sessions[target_session_id]["status"] = "role_ready"
        return {"status": "success"}
    return {"status": "ignored"}

@router.get("/aws-status")
async def check_aws_status(session_id: str):
    """Frontend polls this to know when to submit"""
    session_data = sessions.get(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": session_data.get("status")}

@router.post("/verify-role")
async def verify_aws_role(request: VerifyRoleRequest):
    """Handshake is now entirely automated based on session memory"""
    session_data = sessions.get(request.session_id)

    if not session_data or session_data.get("status") != "role_ready":
        raise HTTPException(status_code=400, detail="Role not ready yet.")

    role_arn = session_data.get("role_arn")
    if not role_arn:
         raise HTTPException(status_code=400, detail="Role ARN is missing.")

    sts_client = boto3.client("sts")

    try:
        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName="CloudAssistantSession",
            ExternalId=session_data["external_id"],
        )

        credentials = response["Credentials"]
        assumed_role_user = response["AssumedRoleUser"]

        sessions[request.session_id].update({
            "status": "active",
            "creds": {
                "access_key": credentials["AccessKeyId"],
                "secret_key": credentials["SecretAccessKey"],
                "session_token": credentials["SessionToken"],
            },
            "account_id": assumed_role_user["Arn"].split(":")[4],
            "user_arn": assumed_role_user["Arn"],
            "region": request.region,
            "pending_actions": {},
            "pending_plans": {},
        })

        return {
            "status": "success",
            "account_id": sessions[request.session_id]["account_id"],
            "user_arn": sessions[request.session_id]["user_arn"],
            "region": sessions[request.session_id]["region"],
        }

    except ClientError as e:
        raise HTTPException(status_code=403, detail=f"Access Denied: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))