# PDF Poly Lingo

AWS-native PDF and HTML translation service using Amazon Translate, S3, and Lambda. Files are uploaded to S3, translated asynchronously, and notifications are sent when ready.

## Architecture

- **Upload**: API Gateway + Lambda generates presigned S3 URLs; client uploads directly to Input bucket
- **Trigger**: S3 event invokes Lambda which starts Amazon Translate batch job (HTML/text) or Textract→Translate for PDF
- **Delivery**: Translated files land in Output bucket; Lambda publishes to SNS for email/WebSocket notification

## Prerequisites

- Python 3.10+
- Node.js 18+ (for CDK CLI)
- AWS account and credentials configured
- Bootstrap CDK: `cdk bootstrap`

## Setup

```bash
pip install -r requirements.txt
npm install -g aws-cdk
cdk synth
cdk deploy PdfPolyLingoPipeline
```

## Pipeline configuration

The CI/CD pipeline uses CDK Pipelines. Configure source via `cdk.json` context or CLI:

```bash
# CodeStar Connection (recommended for GitHub)
cdk deploy --context connection_arn=arn:aws:codestar-connections:REGION:ACCOUNT:connection/ID --context repo=your-org/pdf-poly-lingo

# Or set in cdk.context.json
```

For GitHub without CodeStar, ensure `github-token` exists in Secrets Manager (repo + admin:repo_hook scope).

## Deploying the service directly (no pipeline)

To deploy just the translation service without the pipeline:

```python
# In app.py, add:
from infrastructure.translation_service_stack import TranslationServiceStack
TranslationServiceStack(app, "TranslationService", env=...)
```

Then: `cdk deploy TranslationService`

## IAM

Amazon Translate requires an IAM role with read access to the Input bucket and read/write access to the Output bucket. The stack creates this role and passes it to `StartTextTranslationJob`.

## Supported formats

- **HTML, TXT**: Batch translation (StartTextTranslationJob)
- **PDF**: Textract extraction → batch translation (scanned PDFs supported)

## Cost

- Amazon Translate: ~$15 per 1M characters (batch)
- Textract (for PDF): additional per-page cost
- S3, Lambda, API Gateway: standard pricing
