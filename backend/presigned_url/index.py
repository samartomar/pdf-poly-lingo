"""Generate presigned S3 URLs for direct upload."""

import json
import uuid
import os
import boto3


def handler(event, context):
    """Generate presigned PUT URL for uploading PDF/HTML to Input bucket."""
    body = json.loads(event.get("body") or "{}")
    filename = body.get("filename", "document")
    target_language = body.get("target_language", "es")
    source_language = body.get("source_language") or "auto"

    ext = os.path.splitext(filename)[1].lower() or ".txt"
    request_id = str(uuid.uuid4())
    key = f"uploads/{request_id}/{filename}"

    bucket = os.environ["INPUT_BUCKET"]
    region = os.environ["REGION"]
    s3 = boto3.client("s3", region_name=region)

    url = s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ContentType": _content_type(ext),
            "Metadata": {
                "target-language": target_language,
                "source-language": source_language,
            },
        },
        ExpiresIn=3600,
    )

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({
            "upload_url": url,
            "key": key,
            "request_id": request_id,
        }),
    }


def _content_type(ext):
    mapping = {
        ".html": "text/html",
        ".htm": "text/html",
        ".txt": "text/plain",
        ".pdf": "application/pdf",
    }
    return mapping.get(ext, "application/octet-stream")
