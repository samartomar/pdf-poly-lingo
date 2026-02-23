"""S3 trigger: start Amazon Translate job when file lands in Input bucket."""

import json
import os
import time
from urllib.parse import unquote

import boto3
from botocore.exceptions import ClientError

# Batch translation supports: HTML, plain text, docx, pptx, xlsx, xlf
# PDF requires Textract preprocessing
BATCH_TYPES = {".html", ".htm", ".txt"}
PDF_TYPE = ".pdf"

TRANSLATE_CLIENT = boto3.client("translate")
TEXTRACT_CLIENT = boto3.client("textract")
S3 = boto3.client("s3")
DYNAMO = boto3.resource("dynamodb")


def handler(event, context):
    """Process S3 OBJECT_CREATED events under uploads/ prefix."""
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote(record["s3"]["object"]["key"])
        if not key.startswith("uploads/") or key.endswith("/"):
            continue
        try:
            process_upload(bucket, key, record)
        except Exception as e:
            print(f"Error processing {key}: {e}")
            _record_failure(key, str(e))
            # Return 200 so S3 does not retry; user will see error via /status
    return {"statusCode": 200}


def process_upload(bucket, key, record):
    """Start Translate job for the uploaded file."""
    input_bucket = os.environ["INPUT_BUCKET"]
    output_bucket = os.environ["OUTPUT_BUCKET"]
    temp_bucket = os.environ["TEMP_BUCKET"]
    role_arn = os.environ["TRANSLATE_ROLE_ARN"]
    topic_arn = os.environ["COMPLETION_TOPIC_ARN"]

    ext = "." + key.rsplit(".", 1)[-1].lower() if "." in key else ""
    prefix = key.rsplit("/", 1)[0] + "/"
    input_uri = f"s3://{input_bucket}/{prefix}"
    output_uri = f"s3://{output_bucket}/"

    # Get object metadata (retry for S3 eventual consistency - can take several seconds)
    for attempt in range(8):
        try:
            meta = S3.head_object(Bucket=bucket, Key=key).get("Metadata") or {}
            break
        except ClientError as e:
            if e.response["Error"]["Code"] == "404" and attempt < 7:
                delay = min(2 ** attempt, 32)
                time.sleep(delay)
            else:
                raise
    target_lang = meta.get("target-language", "es")
    source_lang = meta.get("source-language") or "auto"

    target_codes = [target_lang] if target_lang else ["es"]

    if ext in BATCH_TYPES:
        content_type = _content_type(ext)
        job_id = _start_batch_job(
            input_uri=input_uri,
            output_uri=output_uri,
            role_arn=role_arn,
            source_lang=source_lang,
            target_codes=target_codes,
            content_type=content_type,
        )
    elif ext == PDF_TYPE:
        job_id = _process_pdf(
            bucket=bucket,
            key=key,
            input_bucket=input_bucket,
            output_bucket=output_bucket,
            temp_bucket=temp_bucket,
            role_arn=role_arn,
            source_lang=source_lang,
            target_codes=target_codes,
        )
    else:
        raise ValueError(f"Unsupported format: {ext}. Use HTML, TXT, or PDF.")

    # Extract request_id and original filename from key: uploads/{request_id}/filename
    parts = key.split("/")
    request_id = parts[1] if len(parts) >= 2 else None
    original_filename = parts[-1] if parts else "document"

    if request_id and os.environ.get("TABLE_NAME"):
        table = DYNAMO.Table(os.environ["TABLE_NAME"])
        table.put_item(Item={
            "request_id": request_id,
            "job_id": job_id,
            "status": "in_progress",
            "target_language": target_lang,
            "original_filename": original_filename,
        })

    sns = boto3.client("sns")
    sns.publish(
        TopicArn=topic_arn,
        Subject="Translation job started",
        Message=json.dumps({
            "job_id": job_id,
            "key": key,
            "target_language": target_lang,
        }),
    )
    return job_id


def _start_batch_job(input_uri, output_uri, role_arn, source_lang, target_codes, content_type):
    """Start async batch translation job."""
    resp = TRANSLATE_CLIENT.start_text_translation_job(
        JobName=f"pdf-poly-lingo-{int(time.time())}",
        InputDataConfig={
            "S3Uri": input_uri,
            "ContentType": content_type,
        },
        OutputDataConfig={"S3Uri": output_uri},
        DataAccessRoleArn=role_arn,
        SourceLanguageCode=source_lang,
        TargetLanguageCodes=target_codes,
    )
    return resp["JobId"]


def _process_pdf(
    bucket,
    key,
    input_bucket,
    output_bucket,
    temp_bucket,
    role_arn,
    source_lang,
    target_codes,
):
    """Extract text from PDF via Textract, then run batch translation."""
    job_id_txt = f"pdf-extract-{int(time.time())}"
    temp_prefix = f"temp/{job_id_txt}/"

    # Use async StartDocumentTextDetection - supports more PDF formats than sync DetectDocumentText
    response = TEXTRACT_CLIENT.start_document_text_detection(
        DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}}
    )
    textract_job_id = response["JobId"]

    # Poll until complete (max ~5 min for large PDFs)
    for _ in range(60):
        status_resp = TEXTRACT_CLIENT.get_document_text_detection(JobId=textract_job_id)
        status = status_resp["JobStatus"]
        if status == "SUCCEEDED":
            break
        if status == "FAILED":
            raise RuntimeError(
                status_resp.get("StatusMessage", "Textract job failed")
            )
        time.sleep(5)

    if status_resp["JobStatus"] != "SUCCEEDED":
        raise RuntimeError("Textract job timed out")

    # Collect all pages (pagination for multi-page)
    blocks = list(status_resp.get("Blocks", []))
    next_token = status_resp.get("NextToken")
    while next_token:
        page = TEXTRACT_CLIENT.get_document_text_detection(
            JobId=textract_job_id, NextToken=next_token
        )
        blocks.extend(page.get("Blocks", []))
        next_token = page.get("NextToken")

    text_blocks = [b["Text"] for b in blocks if b["BlockType"] == "LINE"]
    full_text = "\n".join(text_blocks) if text_blocks else ""

    if not full_text.strip():
        raise ValueError(
            "No text could be extracted from this PDF. It may be image-only, scanned, or use an unsupported format."
        )

    # Write extracted text to temp bucket
    txt_key = f"{temp_prefix}extracted.txt"
    S3.put_object(
        Bucket=temp_bucket,
        Key=txt_key,
        Body=full_text.encode("utf-8"),
        ContentType="text/plain",
    )

    # Start Translate job on the extracted text
    input_uri = f"s3://{temp_bucket}/{temp_prefix}"
    output_uri = f"s3://{output_bucket}/"
    return _start_batch_job(
        input_uri=input_uri,
        output_uri=output_uri,
        role_arn=role_arn,
        source_lang=source_lang,
        target_codes=target_codes,
        content_type="text/plain",
    )


def _content_type(ext):
    return {
        ".html": "text/html",
        ".htm": "text/html",
        ".txt": "text/plain",
    }.get(ext, "text/plain")


def _record_failure(key: str, error: str) -> None:
    """Write failed status to DynamoDB so /status can return error to user."""
    parts = key.split("/")
    request_id = parts[1] if len(parts) >= 2 else None
    if not request_id or not os.environ.get("TABLE_NAME"):
        return
    try:
        table = DYNAMO.Table(os.environ["TABLE_NAME"])
        table.put_item(Item={
            "request_id": request_id,
            "status": "failed",
            "error": error[:500],  # Limit length
        })
    except Exception as e:
        print(f"Could not record failure for {request_id}: {e}")
