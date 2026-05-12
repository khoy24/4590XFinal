import re
from typing import Any

from botocore.exceptions import ClientError

from app.services.aws_actions import boto_session_from_stored, summarize_response

_BUCKET_NAME_SAFE = re.compile(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$")


def sanitize_bucket_name(name: str) -> str:
    s = " ".join((name or "").strip().split())
    if not s:
        return "cloud-assistant-bucket"
    s = s.lower().replace(" ", "-")
    s = re.sub(r"[^a-z0-9\-]", "", s)
    s = s.strip("-")
    if len(s) < 3:
        s = "cloud-assistant-bucket"
    if len(s) > 63:
        s = s[:63]
    if not _BUCKET_NAME_SAFE.fullmatch(s):
        s = "cloud-assistant-bucket"
    return s


def validate_s3_starter_inputs(
    bucket_name: str,
    region: str | None,
) -> dict[str, str]:
    name = sanitize_bucket_name(bucket_name)
    if region and region not in ["us-east-1", "us-west-1", "us-west-2", "eu-west-1", "eu-central-1"]:
        raise ValueError("Invalid region for S3 bucket.")
    return {
        "bucket_name": name,
        "region": region or "us-east-1",
    }


def security_plan_text_s3_starter(bucket_name: str, region: str, enable_encryption: bool, enable_versioning: bool, block_public_access: bool) -> str:
    plan = f"**S3 bucket starter plan ({bucket_name}) in {region}**\n\n"
    plan += "What will be created:\n"
    plan += f"- S3 bucket named `{bucket_name}`.\n"
    if enable_encryption:
        plan += "- Server-side encryption enabled (AES256).\n"
    if enable_versioning:
        plan += "- Versioning enabled for data protection.\n"
    if block_public_access:
        plan += "- Public access blocked for security.\n"
    plan += "\nSecurity posture:\n"
    plan += "- Bucket is private by default.\n"
    if block_public_access:
        plan += "- All public access is blocked, preventing accidental exposure.\n"
    if enable_encryption:
        plan += "- Data is encrypted at rest.\n"
    if enable_versioning:
        plan += "- Versioning protects against accidental overwrites or deletions.\n"
    plan += "\n**Confirm only if** you intend to create this storage bucket (may incur charges for storage/requests)."
    return plan


def one_result(
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


def run_s3_starter_plan(entry: dict[str, Any], inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """Execute S3 starter workflow in order after user confirmation."""
    boto_sess = boto_session_from_stored(entry)
    s3 = boto_sess.client("s3")
    results: list[dict[str, Any]] = []
    bucket_name = inputs["bucket_name"]
    region = inputs["region"]
    enable_encryption = inputs.get("enable_encryption", True)
    enable_versioning = inputs.get("enable_versioning", False)
    block_public_access = inputs.get("block_public_access", True)

    def exec_op(op_name: str, fn: Any) -> bool:
        try:
            raw = fn()
            out = raw if isinstance(raw, dict) else {}
            summary = summarize_response("s3", op_name, out)
            results.append(one_result("s3", op_name, True, result=summary))
            return True
        except ClientError as e:
            msg = e.response.get("Error", {}).get("Message", str(e))
            results.append(one_result("s3", op_name, False, error=msg))
            return False
        except Exception as e:
            results.append(one_result("s3", op_name, False, error=str(e)))
            return False

    # Create bucket
    def step_create_bucket():
        params = {"Bucket": bucket_name}
        if region != "us-east-1":
            params["CreateBucketConfiguration"] = {"LocationConstraint": region}
        return s3.create_bucket(**params)

    if not exec_op("create_bucket", step_create_bucket):
        return results

    # Block public access
    if block_public_access:
        def step_block_public():
            return s3.put_public_access_block(
                Bucket=bucket_name,
                PublicAccessBlockConfiguration={
                    "BlockPublicAcls": True,
                    "IgnorePublicAcls": True,
                    "BlockPublicPolicy": True,
                    "RestrictPublicBuckets": True,
                },
            )
        if not exec_op("put_public_access_block", step_block_public):
            return results

    # Enable encryption
    if enable_encryption:
        def step_encrypt():
            return s3.put_bucket_encryption(
                Bucket=bucket_name,
                ServerSideEncryptionConfiguration={
                    "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
                },
            )
        if not exec_op("put_bucket_encryption", step_encrypt):
            return results

    # Enable versioning
    if enable_versioning:
        def step_version():
            return s3.put_bucket_versioning(
                Bucket=bucket_name,
                VersioningConfiguration={"Status": "Enabled"},
            )
        exec_op("put_bucket_versioning", step_version)

    results.append(
        one_result(
            "s3_starter",
            "summary",
            True,
            result={
                "Bucket": bucket_name,
                "Region": region,
                "EncryptionEnabled": enable_encryption,
                "VersioningEnabled": enable_versioning,
                "PublicAccessBlocked": block_public_access,
            },
        )
    )
    return results