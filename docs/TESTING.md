# Testing the PDF Poly Lingo Translation Service

## Prerequisites

1. **Deploy the service** – If the pipeline hasn't deployed the Prod stage yet:
   ```powershell
   cd e:\Development\pdf-poly-lingo
   cdk deploy TranslationService --context deploy_direct=true --require-approval never
   ```
   This creates and deploys the TranslationService stack.

2. **Get the API endpoint** from CloudFormation outputs:
   ```powershell
   # If deployed via pipeline (Prod stage)
   aws cloudformation describe-stacks --stack-name Prod-TranslationService --region us-west-2 --query "Stacks[0].Outputs" --output table

   # If deployed directly
   aws cloudformation describe-stacks --stack-name TranslationService --region us-west-2 --query "Stacks[0].Outputs" --output table
   ```
   Look for `ApiEndpoint` (e.g. `https://xxxxx.execute-api.us-west-2.amazonaws.com/prod/`).

---

## Test Flow

### Step 1: Get a presigned upload URL

```powershell
# Replace YOUR_API_ENDPOINT with the ApiEndpoint from outputs
$apiUrl = "YOUR_API_ENDPOINT"
$body = @{
    filename = "test.txt"
    target_language = "es"
    source_language = "auto"
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "$apiUrl/presigned-url" -Method POST -Body $body -ContentType "application/json"
$response
```

Or with **curl**:

```bash
curl -X POST "YOUR_API_ENDPOINT/presigned-url" \
  -H "Content-Type: application/json" \
  -d '{"filename":"test.txt","target_language":"es","source_language":"auto"}'
```

Example response:
```json
{
  "upload_url": "https://input-bucket.s3.us-west-2.amazonaws.com/uploads/xxx/test.txt?...",
  "key": "uploads/xxx/test.txt",
  "request_id": "xxx"
}
```

### Step 2: Upload your file to the presigned URL

Create a test file `test.txt`:
```
Hello world. This is a test document for translation.
```

Then upload (PowerShell):

```powershell
$uploadUrl = $response.upload_url
Invoke-WebRequest -Uri $uploadUrl -Method PUT -InFile "test.txt" -ContentType "text/plain"
```

Or with **curl**:

```bash
curl -X PUT -H "Content-Type: text/plain" --data-binary @test.txt "$UPLOAD_URL"
```

### Step 3: Wait for translation

- **HTML/TXT**: Usually 1–3 minutes
- **PDF**: Longer (Textract + Translate)

Monitor progress:
```powershell
# Check S3 output bucket (replace OUTPUT_BUCKET from stack outputs)
aws s3 ls s3://OUTPUT_BUCKET/ --recursive
```

### Step 4: Download the translated file

```powershell
aws s3 cp s3://OUTPUT_BUCKET/674763518102-TranslateText-JOB_ID/ ./translated-output/ --recursive
```

---

## Optional: Subscribe to SNS for completion alerts

1. In AWS Console → SNS → Topics → "PDF Poly Lingo Translation Complete"
2. Create subscription → Email
3. Enter your email and confirm the subscription
4. You'll get an email when each translation completes

---

## Supported formats & languages

| Format | Supported |
|--------|------------|
| .txt  | ✅ |
| .html, .htm | ✅ |
| .pdf | ✅ (via Textract extraction) |

**Target languages**: `es`, `fr`, `de`, `it`, `pt`, `ja`, `ko`, `zh`, `ar`, `hi`, `ru`, `nl`, `pl`, `tr`, `vi` (ISO codes)
