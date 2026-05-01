from typing import Any

import boto3
from botocore.exceptions import ClientError

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


def needs_user_confirmation(service: str, operation: str) -> bool:
    return (service, operation) in CONFIRMATION_REQUIRED_OPS


def validate_allowlisted_action(
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


def risk_summary_for_action(
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


def boto_session_from_stored(entry: dict[str, Any]) -> boto3.Session:
    """Builds a session using the TEMPORARY credentials from AssumeRole."""
    creds = entry["creds"]
    return boto3.Session(
        aws_access_key_id=creds["access_key"],
        aws_secret_access_key=creds["secret_key"],
        aws_session_token=creds["session_token"],  # required for roles
        region_name=entry.get("region", "us-east-1"),
    )


def summarize_response(service: str, operation: str, out: dict[str, Any]) -> Any:
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


def execute_aws_actions(
    entry: dict[str, Any], actions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Run allowlisted boto3 calls; return one result dict per action."""
    results: list[dict[str, Any]] = []
    boto_sess = boto_session_from_stored(entry)
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
            summary = summarize_response(service, operation, out)
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
