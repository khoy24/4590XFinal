import re
from typing import Any

from botocore.exceptions import ClientError

from app.services.aws_actions import boto_session_from_stored, summarize_response

_INSTANCE_NAME_SAFE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_PRIVATE_SUBNET_TAGS = ["default"]


def sanitize_instance_name(name: str) -> str:
    s = " ".join((name or "").strip().split())
    if not s:
        return "cloud-assistant-ec2"
    s = re.sub(r"[^A-Za-z0-9._-]", "-", s)
    if len(s) > 128:
        s = s[:128]
    if not _INSTANCE_NAME_SAFE.fullmatch(s):
        s = "cloud-assistant-ec2"
    return s


def validate_ec2_starter_inputs(
    instance_name: str,
    instance_type: str,
    assign_public_ip: bool,
    region: str | None,
) -> dict[str, Any]:
    name = sanitize_instance_name(instance_name)
    if region and region not in [
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "us-west-2",
        "eu-west-1",
        "eu-central-1",
    ]:
        raise ValueError("Invalid region for EC2 instance.")
    if not instance_type or not isinstance(instance_type, str):
        raise ValueError("Instance type is required.")
    return {
        "instance_name": name,
        "instance_type": instance_type,
        "assign_public_ip": bool(assign_public_ip),
        "region": region or "us-east-1",
    }


def security_plan_text_ec2_starter(
    instance_name: str,
    region: str,
    instance_type: str,
    assign_public_ip: bool,
) -> str:
    plan = f"**EC2 starter plan ({instance_name}) in {region}**\n\n"
    plan += "What will be created:\n"
    plan += f"- A security group for the instance with outbound internet allowed and no inbound access.\n"
    plan += f"- An EC2 instance of type `{instance_type}` using a public Amazon Linux 2 AMI.\n"
    if assign_public_ip:
        plan += "- The instance may receive a public IP address in a default subnet if available.\n"
    else:
        plan += "- The instance will be launched without an explicit public IP.\n"
    plan += "\nSecurity posture:\n"
    plan += "- The security group will block inbound traffic by default.\n"
    plan += "- Only the minimum resources needed to run a single instance are created.\n"
    plan += "\n**Confirm only if** you intend to provision compute resources in AWS (this may incur EC2 charges)."
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


def choose_latest_amzn2_ami(ec2: Any) -> str:
    images = ec2.describe_images(
        Filters=[
            {"Name": "name", "Values": ["amzn2-ami-hvm-*-x86_64-gp2"]},
            {"Name": "state", "Values": ["available"]},
        ],
        Owners=["amazon"],
    )
    items = images.get("Images", [])
    if not items:
        raise RuntimeError("Could not locate a suitable Amazon Linux 2 AMI.")
    items.sort(key=lambda i: i.get("CreationDate", ""), reverse=True)
    return items[0]["ImageId"]


def find_default_subnet_id(ec2: Any) -> str | None:
    subnets = ec2.describe_subnets(Filters=[{"Name": "default-for-az", "Values": ["true"]}])
    ids = [s.get("SubnetId") for s in subnets.get("Subnets", []) if s.get("SubnetId")]
    return ids[0] if ids else None


def run_ec2_starter_plan(entry: dict[str, Any], inputs: dict[str, Any]) -> list[dict[str, Any]]:
    boto_sess = boto_session_from_stored(entry)
    ec2 = boto_sess.client("ec2")
    results: list[dict[str, Any]] = []
    instance_name = inputs["instance_name"]
    instance_type = inputs["instance_type"]
    assign_public_ip = inputs.get("assign_public_ip", False)
    sg_id: str | None = None
    instance_id: str | None = None

    def exec_op(op_name: str, fn: Any) -> bool:
        nonlocal sg_id, instance_id
        try:
            raw = fn()
            out = raw if isinstance(raw, dict) else {}
            summary = summarize_response("ec2", op_name, out)
            results.append(one_result("ec2", op_name, True, result=summary))
            return True
        except ClientError as e:
            msg = e.response.get("Error", {}).get("Message", str(e))
            results.append(one_result("ec2", op_name, False, error=msg))
            return False
        except Exception as e:
            results.append(one_result("ec2", op_name, False, error=str(e)))
            return False

    def create_security_group():
        nonlocal sg_id
        name = f"cloud-assistant-ec2-{instance_name[:40]}"
        resp = ec2.create_security_group(
            Description="Cloud Assistant EC2 starter security group",
            GroupName=name,
        )
        sg_id = resp.get("GroupId")
        return resp

    #def authorize_egress():
    #    return ec2.authorize_security_group_egress(
    #        GroupId=sg_id,
    #        IpPermissions=[
    #            {
    #                "IpProtocol": "-1",
    #                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
    #            }
    #        ],
    #    )

    if not exec_op("create_security_group", create_security_group):
        return results
    #if not exec_op("authorize_security_group_egress", authorize_egress):
    #    return results

    def tag_security_group():
        return ec2.create_tags(
            Resources=[sg_id],
            Tags=[{"Key": "Name", "Value": instance_name}],
        )

    if not exec_op("create_tags", tag_security_group):
        return results

    image_id = choose_latest_amzn2_ami(ec2)

    def run_instance():
        nonlocal instance_id
        if assign_public_ip:
            subnet_id = find_default_subnet_id(ec2)
            if not subnet_id:
                raise RuntimeError(
                    "No default subnet found for public IP assignment."
                )
            resp = ec2.run_instances(
                ImageId=image_id,
                InstanceType=instance_type,
                MinCount=1,
                MaxCount=1,
                NetworkInterfaces=[
                    {
                        "AssociatePublicIpAddress": True,
                        "DeviceIndex": 0,
                        "SubnetId": subnet_id,
                        "Groups": [sg_id],
                    }
                ],
                TagSpecifications=[
                    {
                        "ResourceType": "instance",
                        "Tags": [
                            {"Key": "Name", "Value": instance_name},
                        ],
                    }
                ],
            )
        else:
            resp = ec2.run_instances(
                ImageId=image_id,
                InstanceType=instance_type,
                MinCount=1,
                MaxCount=1,
                SecurityGroupIds=[sg_id],
                TagSpecifications=[
                    {
                        "ResourceType": "instance",
                        "Tags": [
                            {"Key": "Name", "Value": instance_name},
                        ],
                    }
                ],
            )
        instance_id = resp.get("Instances", [{}])[0].get("InstanceId")
        return resp

    if not exec_op("run_instances", run_instance):
        return results

    results.append(
        one_result(
            "ec2_starter",
            "summary",
            True,
            result={
                "InstanceId": instance_id,
                "SecurityGroupId": sg_id,
                "InstanceType": instance_type,
                "AssignedPublicIp": assign_public_ip,
            },
        )
    )
    return results