# 4590X Final — Cloud Deployment Assistant

Friendly UI prototype for non-security professionals to work with AWS using natural language. The app connects to the user’s AWS account via a **CloudFormation-created IAM role** and **STS AssumeRole** (with an **ExternalId**). A **Gemini**-backed chat turns plain-English requests into **allowlisted** AWS API calls.

## Architecture (short)

- **Frontend** ([`frontend`](frontend)): React + Vite. Connect flow opens CloudFormation quick-create; user pastes the Role ARN from stack outputs.
- **Backend** ([`backend`](backend)): FastAPI. Stores per-tab session state in memory, calls Gemini on `/chat`, executes only operations in `ALLOWED_AWS_ACTIONS` in [`backend/main.py`](backend/main.py).

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

To **revoke** access: delete the CloudFormation stack or the IAM role in the AWS console.

## Common AWS setup errors

- `Unable to locate credentials`: the backend process has no AWS credentials. Run `aws configure`, set `AWS_PROFILE`, or export `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` before starting `uvicorn`.
- `AccessDenied` from `AssumeRole`: credentials exist, but the IAM user policy, role trust policy, `AWS_BACKEND_ACCOUNT_ID`, or ExternalId does not match.
- Modal stuck on `Generating secure link...`: check `frontend/.env`; `VITE_API_URL` should point to the backend, usually `http://127.0.0.1:8000`.
- Stack already exists but connect fails: delete the stack and recreate it from the current quick-create link because the ExternalId is unique per browser session.

## What the chat can do today

The backend allowlist (see [`backend/main.py`](backend/main.py)) includes **read/list/describe** operations on S3, EC2 (instances, security groups, VPCs), IAM users, and STS `GetCallerIdentity`, plus **S3 `create_bucket`**. Anything outside that list is rejected.

## Demo script (class)

1. Explain the problem: AWS security setup is hard for non-experts.
2. Show **Connect to AWS**: CloudFormation + ExternalId + paste Role ARN.
3. Point out **account / region / ARN** after connect.
4. Ask the assistant to **list S3 buckets** or **describe VPCs** (read-only).
5. Optionally show **create bucket** or an error if the role lacks permission.
6. Mention **safety boundaries**: allowlisted APIs only, temporary creds, revoke via stack deletion.

## Gemini / privacy

When you use Unpaid Services, including, for example, Google AI Studio and the unpaid quota on Gemini API, Google uses the content you submit to the Services and any generated responses to provide, improve, and develop Google products and services and machine learning technologies, including Google's enterprise features, products, and services, consistent with our Privacy Policy.

To help with quality and improve our products, human reviewers may read, annotate, and process your API input and output. Google takes steps to protect your privacy as part of this process. This includes disconnecting this data from your Google Account, API key, and Cloud project before reviewers see or annotate it. **Do not submit sensitive, confidential, or personal information** to the Unpaid Services.

## IAM template in repo

[`backend/role-template.yaml`](backend/role-template.yaml) is the logical source for the role; the quick-create URL in the app may point at a copy hosted in S3 — keep them in sync if you change permissions.
