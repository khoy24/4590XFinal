import os
import urllib.parse
import uuid
from typing import Annotated

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import BACKEND_ACCOUNT_ID
from app.crypto_secrets import decrypt_str, encrypt_str
from app.database import get_db
from app.deps import get_active_aws_connection, get_current_user
from app.models import AwsConnection, User
from app.schemas import VerifyRoleRequest, WebhookPayload
from app.services.credential_manager import (
    clear_user_credential_cache,
    get_execution_entry,
)
from app.state import clear_user_workspace

router = APIRouter()

WEBHOOK_DOMAIN = os.getenv("WEBHOOK_DOMAIN")


def mask_arn_display(arn: str | None) -> str | None:
    """Show only resource suffix for STS assumed-role ARN in UI/API."""
    if not arn:
        return None
    parts = arn.split(":")
    if len(parts) < 6:
        return "(connected)"
    return parts[-1]  # session name / role-session trail


def _ensure_webhook_domain() -> str:
    base = WEBHOOK_DOMAIN
    if not base:
        raise HTTPException(
            status_code=500,
            detail="WEBHOOK_DOMAIN is not configured. Set it for CloudFormation webhook.",
        )
    return base.rstrip("/")


def _quick_create_link(external_id: str) -> str:
    if not BACKEND_ACCOUNT_ID:
        raise HTTPException(
            status_code=500,
            detail="AWS_BACKEND_ACCOUNT_ID is not configured.",
        )
    template_url = (
        "https://cloud-assistant-template-1.s3.us-east-1.amazonaws.com/template.yaml"
    )
    encoded_url = urllib.parse.quote(template_url)
    webhook_base = _ensure_webhook_domain()
    webhook_url = f"{webhook_base}/aws-webhook"
    encoded_webhook = urllib.parse.quote(webhook_url)

    return (
        "https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/"
        "quickcreate?"
        f"templateURL={encoded_url}&stackName=CloudAssistant&param_ExternalID={external_id}"
        f"&param_BackendAccountID={BACKEND_ACCOUNT_ID}&param_WebhookURL={encoded_webhook}"
    )


@router.get("/generate-aws-link")
def generate_aws_link(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    conn = db.scalar(select(AwsConnection).where(AwsConnection.user_id == user.id))
    if conn and conn.connect_status == "active":
        raise HTTPException(
            status_code=409,
            detail="Already connected to AWS. Use forget connection before creating a new stack.",
        )

    # Reuse pending or role_ready row so the CF link ExternalId stays valid
    if conn and conn.connect_status in ("pending", "role_ready"):
        external_id = conn.external_id
    else:
        external_id = str(uuid.uuid4())
        conn = AwsConnection(
            user_id=user.id,
            external_id=external_id,
            connect_status="pending",
            encrypted_role_arn=None,
        )
        db.add(conn)
        db.commit()
        db.refresh(conn)

    return {"link": _quick_create_link(external_id)}


@router.post("/aws-webhook")
def receive_aws_webhook(
    payload: WebhookPayload,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """CloudFormation custom resource posts Role ARN + ExternalId."""
    conn = db.scalar(
        select(AwsConnection).where(AwsConnection.external_id == payload.external_id),
    )
    if not conn:
        return {"status": "ignored"}
    if conn.connect_status == "active":
        return {"status": "ignored"}

    conn.encrypted_role_arn = encrypt_str(payload.role_arn)
    conn.connect_status = "role_ready"
    db.add(conn)
    db.commit()
    return {"status": "success"}


@router.get("/aws-status")
def check_aws_status(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    conn = db.scalar(select(AwsConnection).where(AwsConnection.user_id == user.id))
    if not conn:
        raise HTTPException(status_code=404, detail="No AWS connection started.")
    return {"status": conn.connect_status}


@router.post("/verify-role")
def verify_aws_role(
    request: VerifyRoleRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    conn = db.scalar(select(AwsConnection).where(AwsConnection.user_id == user.id))
    if not conn or conn.connect_status != "role_ready":
        raise HTTPException(
            status_code=400,
            detail="Role not ready yet. Finish creating the CloudFormation stack.",
        )
    if not conn.encrypted_role_arn:
        raise HTTPException(status_code=400, detail="Role ARN is missing.")

    role_arn = decrypt_str(conn.encrypted_role_arn)
    region = request.region or "us-east-1"

    sts_client = boto3.client("sts")
    try:
        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName="CloudAssistantSession",
            ExternalId=conn.external_id,
        )
        assumed_role_user = response["AssumedRoleUser"]
        arn = assumed_role_user["Arn"]
        account_id = arn.split(":")[4]

        conn.connect_status = "active"
        conn.aws_account_id = account_id
        conn.user_arn = arn
        conn.region = region
        db.add(conn)
        db.commit()

        # Prime credential cache with this AssumeRole response
        get_execution_entry(user.id, conn)

        return {
            "status": "success",
            "account_id": account_id,
            "user_arn": mask_arn_display(arn),
            "region": region,
        }
    except ClientError as e:
        raise HTTPException(status_code=403, detail=f"Access Denied: {e!s}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/aws-connection/current")
def aws_connection_current(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    conn = db.scalar(select(AwsConnection).where(AwsConnection.user_id == user.id))
    if not conn or conn.connect_status != "active":
        return {
            "connected": False,
            "status": conn.connect_status if conn else None,
        }
    # Refresh STS for cache + get current display fields
    try:
        entry = get_execution_entry(user.id, conn)
    except ClientError:
        return {
            "connected": False,
            "status": "error",
            "detail": "Could not refresh AWS credentials. Check the IAM role and stack.",
        }

    return {
        "connected": True,
        "status": "active",
        "account_id": entry.get("account_id") or conn.aws_account_id,
        "user_arn": mask_arn_display(entry.get("user_arn") or conn.user_arn),
        "region": conn.region,
    }


@router.delete("/aws-connection")
def forget_aws_connection(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    conn = db.scalar(select(AwsConnection).where(AwsConnection.user_id == user.id))
    if conn:
        db.delete(conn)
        db.commit()
    clear_user_credential_cache(user.id)
    clear_user_workspace(user.id)
    return {"status": "ok"}
