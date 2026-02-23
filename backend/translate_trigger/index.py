"""S3 trigger: start Amazon Translate job when file lands in Input bucket."""

import json
import os
import time

import boto3

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
        key = record["s3"]["object"]["key"]
        if not key.startswith("uploads/") or key.endswith("/"):
            continue
        try:
            process_upload(bucket, key, record)
        except Exception as e:
            print(f"Error processing {key}: {e}")
            raise
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

    # Get object metadata for target/source language
    meta = S3.head_object(Bucket=bucket, Key=key).get("Metadata") or {}
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

    # Extract request_id from key: uploads/{request_id}/filename
    parts = key.split("/")
    request_id = parts[1] if len(parts) >= 2 else None

    if request_id and os.environ.get("TABLE_NAME"):
        table = DYNAMO.Table(os.environ["TABLE_NAME"])
        table.put_item(Item={
            "request_id": request_id,
            "job_id": job_id,
            "status": "in_progress",
            "target_language": target_lang,
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

    # Download PDF and run Textract (sync DetectDocumentText for simplicity)
    obj = S3.get_object(Bucket=bucket, Key=key)
    doc_bytes = obj["Body"].read()

    response = TEXTRACT_CLIENT.detect_document_text(Document={"Bytes": doc_bytes})
    text_blocks = [b["Text"] for b in response.get("Blocks", []) if b["BlockType"] == "LINE"]
    full_text = "\n".join(text_blocks)

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
