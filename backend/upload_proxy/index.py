"""Proxy upload: receive file via API. Uses sync TranslateDocument for small HTML/TXT (instant)."""

import base64
import json
import uuid
import os

import boto3

SYNC_MAX_BYTES = 100 * 1024  # 100 KB - TranslateDocument limit

translate_client = boto3.client("translate")
s3_client = boto3.client("s3")
dynamo = boto3.resource("dynamodb")


def handler(event, context):
    """Accept base64 file. If small HTML/TXT, translate sync and return. Else upload to S3."""
    try:
        body = json.loads(event.get("body") or "{}")
        file_b64 = body.get("file")
        filename = body.get("filename", "document")
        target_lang = body.get("target_language", "es")
        source_lang = body.get("source_language") or "auto"

        if not file_b64:
            return _response(400, {"error": "Missing 'file' (base64)"})

        content = base64.b64decode(file_b64)

        ext = os.path.splitext(filename)[1].lower()
        content_type_map = {
            ".html": "text/html",
            ".htm": "text/html",
            ".txt": "text/plain",
            ".pdf": "application/pdf",
        }
        content_type = content_type_map.get(ext, "application/octet-stream")

        # Fast path: small HTML/TXT - sync TranslateDocument (returns in seconds)
        if (
            len(content) <= SYNC_MAX_BYTES
            and content_type in ("text/html", "text/plain")
        ):
            return _translate_sync(content, content_type, filename, target_lang, source_lang)

        # Async path: larger files or PDF - upload to S3
        if len(content) > 5 * 1024 * 1024:
            return _response(400, {"error": "File too large (max 5MB)"})

        request_id = str(uuid.uuid4())
        key = f"uploads/{request_id}/{filename}"
        bucket = os.environ["INPUT_BUCKET"]
        region = os.environ["REGION"]
        s3 = boto3.client("s3", region_name=region)

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

        # Write initial record so /status returns immediately (avoids stuck "pending")
        if os.environ.get("TABLE_NAME"):
            table = dynamo.Table(os.environ["TABLE_NAME"])
            table.put_item(Item={
                "request_id": request_id,
                "status": "processing",
                "target_language": target_lang,
                "original_filename": filename,
            })

        return _response(200, {
            "sync": False,
            "request_id": request_id,
            "key": key,
            "message": "Translation started. Use /status to poll for result.",
        })
    except Exception as e:
        return _response(500, {"error": str(e)})


def _translate_sync(content, content_type, filename, target_lang, source_lang):
    """Use TranslateDocument for instant result."""
    resp = translate_client.translate_document(
        Document={"Content": content, "ContentType": content_type},
        SourceLanguageCode=source_lang,
        TargetLanguageCode=target_lang,
    )
    translated = resp["TranslatedDocument"]["Content"]
    return _response(200, {
        "sync": True,
        "translated_base64": base64.b64encode(translated).decode(),
        "filename": filename,
    })


def _response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body),
    }
