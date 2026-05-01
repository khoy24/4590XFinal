# 4590X Final — Cloud Deployment Assistant

Friendly UI prototype for non-security professionals to work with AWS using natural language. The app connects to the user’s AWS account via a **CloudFormation-created IAM role** and **STS AssumeRole** (with an **ExternalId**). A **Gemini**-backed chat turns plain-English requests into **allowlisted** AWS API calls.

## Architecture (short)

- **Frontend** ([`frontend`](frontend)): React + Vite. Connect flow opens CloudFormation quick-create; user pastes the Role ARN from stack outputs. After connect, **Guided VPC starter** submits a staged plan and confirms it from the chat panel.
- **Backend** ([`backend`](backend)): FastAPI. Stores per-tab session state in memory, calls Gemini on `/chat`, executes allowlisted operations. **Write** actions such as `s3.create_bucket` are staged until `POST /confirm-action`. The VPC starter workflow uses `POST /plan-vpc-starter` plus `POST /confirm-plan`.

## HTTP API overview

| Method | Path | Purpose |
| ------ | ----- | ------- |
| `GET` | `/generate-aws-link` | CloudFormation quick-create URL + session external ID |
| `POST` | `/verify-role` | AssumeRole into the user stack’s role |
| `POST` | `/chat` | Gemini + allowlisted AWS calls (writes may be staged) |
| `POST` | `/confirm-action` | Run one staged chat write action (`action_id`) |
| `POST` | `/plan-vpc-starter` | Validate inputs and stage a VPC starter **plan** (`plan_id`) |
| `POST` | `/confirm-plan` | Run the staged VPC starter sequence |

## Prerequisites

- Node.js and npm (for the frontend)
- Python 3 and pip (for the backend)
- A **Gemini API key** ([Google AI Studio](https://aistudio.google.com/))
- For AWS: the **account ID** of the machine/user that runs the backend (used as `AWS_BACKEND_ACCOUNT_ID` in the CloudFormation template trust policy)
- AWS credentials configured for the **backend host** (environment variables, `~/.aws/credentials`, or IAM role) so it can call `sts:AssumeRole` into the role the user creates in **their** account
- Optional but recommended: the **AWS CLI**, so you can run `aws configure` locally

## Environment variables

### Backend ([`backend/.env.example`](backend/.env.example))

| Variable | Purpose |
| -------- | ------- |
| `GEMINI_API_KEY` | Google Gemini API key |
| `AWS_BACKEND_ACCOUNT_ID` | AWS account ID trusted in the user’s role template (quick-create link) |

### Frontend ([`frontend/.env.example`](frontend/.env.example))

| Variable | Purpose |
| -------- | ------- |
| `VITE_API_URL` | Backend base URL, e.g. `http://127.0.0.1:8000` |

Create `.env` files:

```bash
cd backend && cp .env.example .env
cd ../frontend && cp .env.example .env
```

Edit both files with real values.

## Local AWS credentials for the backend

The backend uses `boto3` to call AWS STS, so the **same terminal/process that runs `uvicorn`** needs AWS credentials before the app can verify a pasted Role ARN.

Do **not** use root access keys. For a local demo, create an IAM user such as `cloud-assistant-local-backend`, then attach an inline policy that allows it to assume the CloudAssistant role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::<YOUR_AWS_ACCOUNT_ID>:role/CloudAssistantRole-us-east-1"
    }
  ]
}
```

Then create an access key for that IAM user.

If the AWS CLI is installed, configure the credentials:

```bash
aws configure
```

If `aws configure` says `command not found`, install the AWS CLI or export the IAM user's credentials directly in the backend terminal before starting the server:

```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_DEFAULT_REGION="us-east-1"
uvicorn main:app --reload
```

These credentials belong to the backend host. Users should paste only the **Role ARN** from CloudFormation into the app, never long-term AWS access keys.

## Install and run

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Default API: `http://127.0.0.1:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Default UI: `http://localhost:5173` (CORS is configured for this origin in the backend).

## Connecting AWS (user flow)

1. Click **Connect to AWS** in the app.
2. Open the generated **CloudFormation quick-create** link. Complete the stack (acknowledge and create). The template is parameterized with an **ExternalId** unique to this browser session.
3. From the stack **Outputs**, copy the **Role ARN**.
4. Paste the Role ARN into the modal and submit. The backend calls **AssumeRole** and stores **temporary** credentials in **server memory** for that session.
5. After success, the sidebar shows **account ID**, **region**, and **assumed-role ARN** returned from `/verify-role`.
6. **Guided VPC starter** appears in the sidebar: configure name/CIDR fields and click **Preview plan in chat** to review security notes in the thread, then **Confirm plan**.

To **revoke** access: delete the CloudFormation stack or the IAM role in the AWS console.

## Guided VPC starter

For a concrete “secure network basics” demo without expecting the user to know AWS networking APIs:

1. Connect AWS so the sidebar shows region and account.
2. Fill in **project name** and optional CIDRs (defaults: `10.0.0.0/16`, public `10.0.1.0/24`, private `10.0.2.0/24`). **Region** must match the connected session (`/verify-role`).
3. **Preview plan in chat** — the backend validates CIDR containment and overlaps, then stages a pending plan (`POST /plan-vpc-starter`).
4. In the chat bubble, **Confirm plan** runs the sequence in AWS (`POST /confirm-plan`): VPC (DNS enabled), subnets, Internet Gateway, public routing to `0.0.0.0/0`, and Name tags.

**Limits (prototype):** no rollback if a midpoint API fails; leftover resources may remain in AWS. Private subnets **do not** get a NAT Gateway or outbound routing. Sessions are **in-memory only** — restart clears pending plans/actions.

Gemini `/chat` is instructed **not** to emit EC2 VPC **write** operations; use this guided flow for provisioning.

## Common AWS setup errors

- `Unable to locate credentials`: the backend process has no AWS credentials. Run `aws configure`, set `AWS_PROFILE`, or export `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` before starting `uvicorn`.
- `AccessDenied` from `AssumeRole`: credentials exist, but the IAM user policy, role trust policy, `AWS_BACKEND_ACCOUNT_ID`, or ExternalId does not match.
- Modal stuck on `Generating secure link...`: check `frontend/.env`; `VITE_API_URL` should point to the backend, usually `http://127.0.0.1:8000`.
- Stack already exists but connect fails: delete the stack and recreate it from the current quick-create link because the ExternalId is unique per browser session.

## Write actions and plans need your confirmation

Read-only calls (list buckets, describe VPCs, etc.) run as soon as you send the chat message.

- **Chat write:** **S3 `create_bucket`** is staged first — the assistant shows a **Review before running** card. Nothing executes until **Confirm**.
- **Guided VPC:** the full VPC sequence is staged as one **plan**. **Confirm plan** runs multiple EC2 APIs in order; **Cancel** only dismisses the UI (discard the staged `plan_id` on the backend by not confirming — a new preview creates a fresh plan).

**Cancel** on a bucket card dismisses without calling AWS.

APIs: `POST /confirm-action` (`session_id`, `action_id`) and `POST /confirm-plan` (`session_id`, `plan_id`) — see [`backend/app/routers/chat.py`](backend/app/routers/chat.py) and [`backend/app/routers/vpc_starter.py`](backend/app/routers/vpc_starter.py).

## What the chat can do today

The backend allowlist (see [`backend/app/services/aws_actions.py`](backend/app/services/aws_actions.py)) includes **read/list/describe** on S3, EC2 (`describe_instances`, `describe_security_groups`, `describe_vpcs`, `describe_route_tables`), IAM users, STS `GetCallerIdentity`, plus **S3 `create_bucket`** (staged → confirm).

**VPC networking writes** (VPC, subnets, IGW, routes, tags) are **not** meant to come from Gemini; they run only via **Guided VPC starter** → `confirm-plan`.

Anything outside the allowlist is rejected.

## Demo script (class)

1. Explain the problem: AWS security setup is hard for non-experts.
2. Show **Connect to AWS**: CloudFormation + ExternalId + paste Role ARN.
3. Point out **account / region / ARN** after connect.
4. Ask the assistant to **list S3 buckets** or **describe VPCs** (read-only; runs immediately).
5. Optionally run **Guided VPC starter**: preview plan in chat → **Confirm plan**, then inspect **account / VPC / subnet IDs** in the results list.
6. Ask to **create a bucket** with a specific name — show the **pending** card, then **Confirm** (or Cancel).
7. Mention **safety boundaries**: allowlisted APIs only, staged writes/plans + confirmation, temporary creds, least-privilege role template (`role-template.yaml`), revoke via stack deletion.

## Gemini / privacy

When you use Unpaid Services, including, for example, Google AI Studio and the unpaid quota on Gemini API, Google uses the content you submit to the Services and any generated responses to provide, improve, and develop Google products and services and machine learning technologies, including Google's enterprise features, products, and services, consistent with our Privacy Policy.

To help with quality and improve our products, human reviewers may read, annotate, and process your API input and output. Google takes steps to protect your privacy as part of this process. This includes disconnecting this data from your Google Account, API key, and Cloud project before reviewers see or annotate it. **Do not submit sensitive, confidential, or personal information** to the Unpaid Services.

## IAM template in repo

[`backend/role-template.yaml`](backend/role-template.yaml) grants an **inline** least-privilege policy aligned with this prototype: STS `GetCallerIdentity`, narrow S3, EC2 reads + VPC-starter writes, and IAM **read-only** listing/get user. Broad managed policies (**not** CloudFormation administrative access on this role) are intentionally omitted—the stack is created **by the user in the AWS console**, not via this IAM role.

The quick-create URL in the app points at an S3-hosted copy of this template — **upload the updated YAML** there if your demo uses hosted quick-create ([`backend/app/routers/aws_auth.py`](backend/app/routers/aws_auth.py) `template_url`).
