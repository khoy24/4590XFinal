# 4590X Final — Cloud Deployment Assistant

Friendly UI prototype for non-security professionals to work with AWS using natural language. The app connects to the user’s AWS account via a **CloudFormation-created IAM role** and **STS AssumeRole** (with an **ExternalId**). A **Gemini**-backed chat turns plain-English requests into **allowlisted** AWS API calls.

## Project Proposal 

Our group will develop a friendly user interface prototype designed for non-security
professionals to deploy systems to AWS securely. The application will leverage the Gemini API
to translate natural language prompts into secure cloud configurations. By allowing users to
describe their needs in plain language, we make complex tasks easier. This ensures that users
with little to no technical expertise can still use the functionality that AWS offers.

The interface will feature a chat-based assistant where users can ask questions and trigger the
programmatic setup of various AWS services. To maintain high security standards, the system
will identify "necessary inputs" that cannot be inferred, such as specific privacy settings or
authentication credentials, and prompt the user for manual selection. For these manual choices,
the interface will provide explanations to educate the user on the security implications of their
decisions. The final system will demonstrate how combining Large Language Models (LLMs)
with AWS domain language can automate the creation of a reliable, secure cloud environment
for non-technical users.

## Architecture

- **Frontend** ([`frontend`](frontend)): React + Vite. **Register/sign in**, then CloudFormation quick-create (webhook registers the Role ARN). After connect, **Guided VPC starter** submits a staged plan and confirms it from the chat panel.
- **Backend** ([`backend`](backend)): FastAPI. **SQLite** stores accounts and encrypted IAM Role ARNs; **HttpOnly cookie** sessions; STS temporary credentials cached **in memory** per logged-in user and refreshed automatically. Gemini on `/chat`, allowlisted boto3. Writes such as `s3.create_bucket` are staged until `POST /confirm-action`. VPC starter uses `POST /plan-vpc-starter` and `POST /confirm-plan`.

## Authentication

Users **register/login** (`POST /auth/register`, `POST /auth/login`). The backend sets `cda_session` (HttpOnly, SameSite=lax). All AWS endpoints require this cookie (`credentials: "include"` from the SPA).

Set **`APP_SECRET_KEY`** (≥16 chars) and **`APP_ENCRYPTION_KEY`** (Fernet — see `.env.example`) in `backend/.env`.

## HTTP API overview

| Method | Path                        | Purpose                                                |
| ------ | --------------------------- | ------------------------------------------------------ |
| `POST` | `/auth/register`            | Register; sets session cookie                          |
| `POST` | `/auth/login`               | Login; sets session cookie                             |
| `POST` | `/auth/logout`              | Clear cookie and in-memory STS cache                   |
| `GET`  | `/auth/me`                  | Current user or `null`                                 |
| `GET` | `/generate-aws-link`       | CF quick-create URL (authenticated)                    |
| `GET` | `/aws-status`               | `pending` / `role_ready` / `active` for current user   |
| `POST` | `/verify-role`               | AssumeRole; persist encrypted role metadata            |
| `GET`  | `/aws-connection/current`    | Restore “connected” UI after reload                    |
| `DELETE`| `/aws-connection`           | Forget stored AWS connection for this account          |
| `POST` | `/chat`                     | Gemini + allowlisted AWS (cookies, no session_id body) |
| `POST` | `/confirm-action`           | Confirm staged chat write (`action_id` only)           |
| `POST` | `/plan-vpc-starter`         | Stage VPC starter plan (`plan_id`)                   |
| `POST` | `/confirm-plan`             | Run the staged VPC sequence                            |

## Prerequisites

- Node.js and npm (for the frontend)
- Python 3 and pip (for the backend)
- ngrok installed and authentication token set up
- A **Gemini API key** ([Google AI Studio](https://aistudio.google.com/))
- For AWS: the **account ID** of the machine/user that runs the backend (used as `AWS_BACKEND_ACCOUNT_ID` in the CloudFormation template trust policy)
- AWS credentials configured for the **backend host** (environment variables, `~/.aws/credentials`, or IAM role) so it can call `sts:AssumeRole` into the role the user creates in **their** account
- Optional but recommended: the **AWS CLI**, so you can run `aws configure` locally

### Setting up ngrok

Download ngrok from ngrok.com after creating a free account

Configure your authentication token in the ngrok browser

```bash
ngrok config add-authtoken your_super_long_token_here
```

## Environment variables

### Backend ([`backend/.env.example`](backend/.env.example))

| Variable                 | Purpose                                                                |
| ------------------------ | ---------------------------------------------------------------------- |
| `GEMINI_API_KEY`           | Google Gemini API key                                                       |
| `AWS_BACKEND_ACCOUNT_ID` | AWS account ID trusted in the user’s role template (quick-create link)     |
| `WEBHOOK_DOMAIN`         | Public base URL for the FastAPI webhook (e.g. ngrok URL, no trailing slash) |
| `APP_SECRET_KEY`         | ≥16 chars; signs session cookie                                              |
| `APP_ENCRYPTION_KEY`     | Fernet key; encrypts IAM Role ARN at rest in SQLite                           |
| `DATABASE_URL`           | Optional; default `sqlite:///./app.db` (created next to cwd when starting server) |

The backend must persist `app.db`; run `uvicorn` from [`backend`](backend/) so SQLite path is predictable.

### Frontend ([`frontend/.env.example`](frontend/.env.example))

| Variable       | Purpose                                        |
| -------------- | ---------------------------------------------- |
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

You will need to have 3 terminals running. One for the backend, one for the frontend, and one for ngrok.

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

### ngrok

```bash
ngrok http 8000
```

The result of this command will paste a link after Forwarding.
(Forwarding link -> your_local_host)
Copy and paste this link into your WEBHOOK_DOMAIN variable in your backend .env file.

## Connecting AWS (user flow)

1. **Register or sign in** (session cookie identifies you across reloads).
2. Choose the **default region** used for STS/boto calls after connection.
3. Click **Connect to AWS** and open the **CloudFormation quick-create** link. Complete the stack. The stack is parameterized with an **ExternalId** tied to **your logged-in account** (reused if you reopen the modal while still disconnecting/reconnecting the same pending link).
4. Wait in the app. When the stack finishes, a Lambda Custom Resource POSTs the **Role ARN** to `/aws-webhook`; the backend stores it **encrypted** in SQLite.
5. The app calls **`/verify-role`**, runs **AssumeRole**, and stores **temporary** credentials only in **server memory** (refreshed automatically before expiry).
6. After success, the sidebar shows **account ID**, **region**, and a short **role session** label. **Guided VPC starter** appears when connected.
7. After a **backend restart**, sign in again and call **`GET /aws-connection/current`** (done automatically) — no new stack unless you **Forget AWS** or delete the stack in AWS.

Use **Forget AWS connection** in the sidebar to remove the encrypted row from the app (you must still delete the CloudFormation stack in AWS to revoke IAM trust).

To **fully revoke** access: delete the CloudFormation stack or the IAM role in the AWS console.

## Guided VPC starter

For a concrete “secure network basics” demo without expecting the user to know AWS networking APIs:

1. Connect AWS so the sidebar shows region and account.
2. Fill in **project name** and optional CIDRs (defaults: `10.0.0.0/16`, public `10.0.1.0/24`, private `10.0.2.0/24`). **Region** must match the connected session (`/verify-role`).
3. **Preview plan in chat** — the backend validates CIDR containment and overlaps, then stages a pending plan (`POST /plan-vpc-starter`).
4. In the chat bubble, **Confirm plan** runs the sequence in AWS (`POST /confirm-plan`): VPC (DNS enabled), subnets, Internet Gateway, public routing to `0.0.0.0/0`, and Name tags.

**Limits (prototype):** no rollback if a midpoint API fails; leftover resources may remain in AWS. Private subnets **do not** get a NAT Gateway or outbound routing. Pending chat writes / VPC plans are **in-memory** — backend restart clears them; the encrypted AWS connection survives in SQLite.

Gemini `/chat` is instructed **not** to emit EC2 VPC **write** operations; use this guided flow for provisioning.

**Operational note:** webhooks bind by `ExternalId` in SQLite. Use a stable public **WEBHOOK_DOMAIN** — if webhook hits another environment, use **Forget AWS connection** then create a fresh quick-create link.

## Common AWS setup errors

- `Unable to locate credentials`: the backend process has no AWS credentials. Run `aws configure`, set `AWS_PROFILE`, or export `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` before starting `uvicorn`.
- `AccessDenied` from `AssumeRole`: credentials exist, but the IAM user policy, role trust policy, `AWS_BACKEND_ACCOUNT_ID`, or ExternalId does not match.
- Modal stuck on `Generating secure link...`: check `frontend/.env`; `VITE_API_URL` should point to the backend, usually `http://127.0.0.1:8000`.

## Write actions and plans need your confirmation

Read-only calls (list buckets, describe VPCs, etc.) run as soon as you send the chat message.

- **Chat write:** **S3 `create_bucket`** is staged first — the assistant shows a **Review before running** card. Nothing executes until **Confirm**.
- **Guided VPC:** the full VPC sequence is staged as one **plan**. **Confirm plan** runs multiple EC2 APIs in order; **Cancel** only dismisses the UI (discard the staged `plan_id` on the backend by not confirming — a new preview creates a fresh plan).

**Cancel** on a bucket card dismisses without calling AWS.

APIs: `POST /confirm-action` (`action_id`) and `POST /confirm-plan` (`plan_id`) with session cookie auth — see [`backend/app/routers/chat.py`](backend/app/routers/chat.py) and [`backend/app/routers/vpc_starter.py`](backend/app/routers/vpc_starter.py).

## What the chat can do today

The backend allowlist (see [`backend/app/services/aws_actions.py`](backend/app/services/aws_actions.py)) includes **read/list/describe** on S3, EC2 (`describe_instances`, `describe_security_groups`, `describe_vpcs`, `describe_route_tables`), IAM users, STS `GetCallerIdentity`, plus **S3 `create_bucket`** (staged → confirm).

**VPC networking writes** (VPC, subnets, IGW, routes, tags) are **not** meant to come from Gemini; they run only via **Guided VPC starter** → `confirm-plan`.

Anything outside the allowlist is rejected.

## Demo script (class)

1. Explain the problem: AWS security setup is hard for non-experts.
2. Show **sign in + Connect to AWS**: CloudFormation + ExternalId + encrypted Role ARN + AssumeRole.
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
