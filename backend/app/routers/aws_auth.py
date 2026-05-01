import uuid
import urllib.parse

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException

from app.config import BACKEND_ACCOUNT_ID
from app.schemas import VerifyRoleRequest
from app.state import sessions

router = APIRouter()


@router.get("/generate-aws-link")
async def generate_aws_link(user_id: str):
    """Generates the link and stores the required External ID."""
    if not BACKEND_ACCOUNT_ID:
        raise HTTPException(status_code=500, detail="Backend not configured correctly.")

    unique_external_id = str(uuid.uuid4())

    sessions[user_id] = {
        "status": "pending",
        "external_id": unique_external_id,
    }

    # gist URL / yaml template (change this to a new S3 bucket if you need to change yaml)
    template_url = "https://ryan-cloud-assistant-templates.s3.us-east-1.amazonaws.com/template.yaml"
    encoded_url = urllib.parse.quote(template_url)
    template_link = f"https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/quickcreate?templateURL={encoded_url}&stackName=CloudAssistant&param_ExternalID={unique_external_id}&param_BackendAccountID={BACKEND_ACCOUNT_ID}"

    return {"link": template_link}


@router.post("/verify-role")
async def verify_aws_role(request: VerifyRoleRequest):
    """Performs the handshake and stores temporary credentials."""
    session_data = sessions.get(request.session_id)

    if not session_data or session_data.get("status") != "pending":
        raise HTTPException(
            status_code=400,
            detail="Invalid session. Please reopen the connection modal.",
        )

    sts_client = boto3.client("sts")

    try:
        response = sts_client.assume_role(
            RoleArn=request.role_arn,
            RoleSessionName="CloudAssistantSession",
            ExternalId=session_data["external_id"],
        )

        credentials = response["Credentials"]
        assumed_role_user = response["AssumedRoleUser"]

        sessions[request.session_id] = {
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
