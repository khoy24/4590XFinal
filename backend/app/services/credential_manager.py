"""In-memory STS credential cache; never persist temporary AWS keys."""

from __future__ import annotations

import datetime as dt
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.crypto_secrets import decrypt_str
from app.models import AwsConnection

# user_id -> execution entry compatible with aws_actions.boto_session_from_stored
_cache: dict[int, dict[str, Any]] = {}

_REFRESH_SKEW = dt.timedelta(minutes=5)


def clear_user_credential_cache(user_id: int) -> None:
    _cache.pop(user_id, None)


def _expired(entry: dict[str, Any]) -> bool:
    exp = entry.get("cred_expires_at")
    if not exp:
        return True
    if getattr(exp, "tzinfo", None) is None:
        exp = exp.replace(tzinfo=dt.UTC)
    return dt.datetime.now(dt.UTC) >= exp - _REFRESH_SKEW


def get_execution_entry(user_id: int, conn: AwsConnection) -> dict[str, Any]:
    """AssumeRole (or reuse cache) and return dict for boto_session_from_stored."""
    if conn.connect_status != "active":
        raise ValueError("AWS connection is not active.")
    if not conn.encrypted_role_arn:
        raise ValueError("Role ARN is missing.")

    cached = _cache.get(user_id)
    if cached and not _expired(cached):
        # Region may change on reconnect
        cached["region"] = conn.region or cached.get("region", "us-east-1")
        return cached

    role_arn = decrypt_str(conn.encrypted_role_arn)
    sts_client = boto3.client("sts")
    try:
        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName="CloudAssistantSession",
            ExternalId=conn.external_id,
        )
    except ClientError:
        clear_user_credential_cache(user_id)
        raise

    credentials = response["Credentials"]
    assumed_role_user = response["AssumedRoleUser"]
    arn = assumed_role_user["Arn"]
    account_id = arn.split(":")[4]
    exp = credentials["Expiration"]
    if getattr(exp, "tzinfo", None) is None:
        exp = exp.replace(tzinfo=dt.UTC)

    region = conn.region or "us-east-1"
    entry: dict[str, Any] = {
        "creds": {
            "access_key": credentials["AccessKeyId"],
            "secret_key": credentials["SecretAccessKey"],
            "session_token": credentials["SessionToken"],
        },
        "region": region,
        "account_id": account_id,
        "user_arn": arn,
        "cred_expires_at": exp,
    }
    _cache[user_id] = entry
    return entry
