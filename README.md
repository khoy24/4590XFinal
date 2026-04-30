# Project Description

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

# Project Setup

You will need to create a Gemini API Key in Google AI Studio, and replace it with the placeholder in the .env file.

### Creating both of the initial .env files

You will have to fill the contents in later

```bash
cd backend
cp .env.example .env

cd ..
cd frontend
cp .env.example .env
```

## Run the Frontend

```bash
cd frontend
npm run dev
```

## Run the Backend

```bash
cd backend
uvicorn main:app --reload
```

## Installing Packages

### Install Backend Dependencies

1. Open your terminal
2. Navigate to the backend folder:

```bash
cd backend
```

3. Install the required packages:

```bash
pip install -r requirements.txt
```

## Gemini

When you use Unpaid Services, including, for example, Google AI Studio and the unpaid quota on Gemini API, Google uses the content you submit to the Services and any generated responses to provide, improve, and develop Google products and services and machine learning technologies, including Google's enterprise features, products, and services, consistent with our Privacy Policy.

To help with quality and improve our products, human reviewers may read, annotate, and process your API input and output. Google takes steps to protect your privacy as part of this process. This includes disconnecting this data from your Google Account, API key, and Cloud project before reviewers see or annotate it. Do not submit sensitive, confidential, or personal information to the Unpaid Services.
