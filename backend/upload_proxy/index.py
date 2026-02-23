"""Proxy upload: receive file via API, upload to S3. Avoids browser S3 CORS."""

import base64
import json
import uuid
import os

import boto3


def handler(event, context):
    """Accept base64 file in JSON body, upload to S3."""
    try:
        body = json.loads(event.get("body") or "{}")
        file_b64 = body.get("file")
        filename = body.get("filename", "document")
        target_lang = body.get("target_language", "es")
        source_lang = body.get("source_language") or "auto"

        if not file_b64:
            return _response(400, {"error": "Missing 'file' (base64)"})

        content = base64.b64decode(file_b64)
        if len(content) > 5 * 1024 * 1024:
            return _response(400, {"error": "File too large (max 5MB)"})

        request_id = str(uuid.uuid4())
        key = f"uploads/{request_id}/{filename}"

        bucket = os.environ["INPUT_BUCKET"]
        region = os.environ["REGION"]
        s3 = boto3.client("s3", region_name=region)

        ext = os.path.splitext(filename)[1].lower()
        content_type = {
            ".html": "text/html",
            ".htm": "text/html",
            ".txt": "text/plain",
            ".pdf": "application/pdf",
        }.get(ext, "application/octet-stream")

        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
            Metadata={
                "target-language": target_lang,
                "source-language": source_lang,
            },
        )

        return _response(200, {"request_id": request_id, "key": key})
    except Exception as e:
        return _response(500, {"error": str(e)})


def _response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body),
    }
