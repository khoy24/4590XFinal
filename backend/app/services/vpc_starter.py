import ipaddress
import re
from typing import Any

from botocore.exceptions import ClientError

from app.services.aws_actions import boto_session_from_stored, summarize_response

_TAGS_SAFE = re.compile(r"^[A-Za-z0-9 ._:/=+\-@]{1,256}$")


def sanitize_project_tag(name: str) -> str:
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


def parse_ipv4_cidr(block: str) -> ipaddress.IPv4Network:
    """Parse CIDR block; raises ValueError if invalid."""
    n = ipaddress.ip_network(block.strip(), strict=False)
    if not isinstance(n, ipaddress.IPv4Network):
        raise ValueError("Only IPv4 CIDR blocks are supported.")
    return n


def validate_vpc_starter_inputs(
    vpc_cidr: str,
    public_cidr: str,
    private_cidr: str,
) -> dict[str, str]:
    vpc_net = parse_ipv4_cidr(vpc_cidr)
    pub_net = parse_ipv4_cidr(public_cidr)
    prv_net = parse_ipv4_cidr(private_cidr)
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


def security_plan_text_vpc_starter(project: str, region: str, cidrs: dict[str, str]) -> str:
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


def run_vpc_starter_plan(entry: dict[str, Any], inputs: dict[str, str]) -> list[dict[str, Any]]:
    """Execute VPC starter workflow in order after user confirmation."""
    boto_sess = boto_session_from_stored(entry)
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
        one_result(
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
