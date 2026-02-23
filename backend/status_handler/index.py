"""Status API: get translation job status and download URL."""

import json
import os

import boto3
from botocore.exceptions import ClientError

DYNAMO = boto3.resource("dynamodb")
S3 = boto3.client("s3")
TRANSLATE = boto3.client("translate")


def handler(event, context):
    """GET ?request_id=xxx returns status and optional download URL."""
    request_id = (event.get("queryStringParameters") or {}).get("request_id")
    if not request_id:
        return _response(400, {"error": "Missing request_id"})

    table_name = os.environ["TABLE_NAME"]
    output_bucket = os.environ["OUTPUT_BUCKET"]
    table = DYNAMO.Table(table_name)

    try:
        row = table.get_item(Key={"request_id": request_id}).get("Item")
    except Exception as e:
        return _response(500, {"error": str(e)})

    if not row:
        return _response(200, {"status": "pending", "request_id": request_id})

    status = row.get("status", "pending")
    job_id = row.get("job_id")

    # Fallback: if stuck in_progress, check Translate job and output bucket directly
    if status in ("in_progress", "processing") and job_id:
        output_key, output_bucket = _check_translate_complete(
            job_id, output_bucket, table, request_id
        )
        if output_key and output_bucket:
            status = "complete"
            row = {"output_key": output_key, "output_bucket": output_bucket, **row}

    result = {
        "request_id": request_id,
        "status": status,
        "job_id": job_id,
    }
    if status == "failed" and row.get("error"):
        result["error"] = row["error"]

    if status == "complete" and row.get("output_key") and row.get("output_bucket"):
        params = {
            "Bucket": row["output_bucket"],
            "Key": row["output_key"],
            "ResponseContentDisposition": _build_content_disposition(row),
        }
        ext = os.path.splitext(row["output_key"].split("/")[-1])[1].lower()
        if ext in (".txt",):
            params["ResponseContentType"] = "text/plain; charset=utf-8"
        elif ext in (".html", ".htm"):
            params["ResponseContentType"] = "text/html; charset=utf-8"
        url = S3.generate_presigned_url("get_object", Params=params, ExpiresIn=3600)
        result["download_url"] = url

    return _response(200, result)


def _check_translate_complete(job_id, output_bucket, table, request_id):
    """If Translate job is done, find output file, update DynamoDB, return (key, bucket)."""
    try:
        resp = TRANSLATE.describe_text_translation_job(JobId=job_id)
        job_status = resp.get("TextTranslationJobProperties", {}).get("JobStatus")
        if job_status != "COMPLETED":
            return None, None
    except ClientError:
        return None, None

    # List output bucket, find the translated file (skip auxiliary metadata, prefer content files)
    try:
        paginator = S3.get_paginator("list_objects_v2")
        best_key = None
        best_size = -1
        for page in paginator.paginate(Bucket=output_bucket):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                size = obj.get("Size", 0)
                if (
                    job_id in key
                    and not key.endswith(".auxiliary-translation-details.json")
                    and "/details/" not in key
                    and size > best_size
                ):
                    best_key, best_size = key, size
        if best_key:
            table.update_item(
                Key={"request_id": request_id},
                UpdateExpression="SET #s = :s, output_key = :k, output_bucket = :b",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":s": "complete",
                    ":k": best_key,
                    ":b": output_bucket,
                },
            )
            return best_key, output_bucket
    except ClientError:
        pass
    return None, None


def _build_content_disposition(row):
    """Build Content-Disposition for download: originalname_translated_es.txt"""
    output_key = row.get("output_key", "")
    original = row.get("original_filename", "document")
    target_lang = row.get("target_language", "es")
    base = os.path.splitext(original)[0] or "document"
    ext = os.path.splitext(output_key.split("/")[-1])[1] or ".txt"
    filename = f"{base}_translated_{target_lang}{ext}"
    return f'attachment; filename="{filename}"'


def _response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body),
    }
