"""Status API: get translation job status and download URL."""

import json
import os

import boto3

DYNAMO = boto3.resource("dynamodb")
S3 = boto3.client("s3")


def handler(event, context):
    """GET ?request_id=xxx returns status and optional download URL."""
    request_id = (event.get("queryStringParameters") or {}).get("request_id")
    if not request_id:
        return _response(400, {"error": "Missing request_id"})

    table_name = os.environ["TABLE_NAME"]
    output_bucket = os.environ["OUTPUT_BUCKET"]
    region = os.environ["REGION"]
    table = DYNAMO.Table(table_name)

    try:
        row = table.get_item(Key={"request_id": request_id}).get("Item")
    except Exception as e:
        return _response(500, {"error": str(e)})

    if not row:
        return _response(200, {"status": "pending", "request_id": request_id})

    status = row.get("status", "pending")
    result = {
        "request_id": request_id,
        "status": status,
        "job_id": row.get("job_id"),
    }
    if status == "failed" and row.get("error"):
        result["error"] = row["error"]

    if status == "complete" and row.get("output_key") and row.get("output_bucket"):
        url = S3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": row["output_bucket"],
                "Key": row["output_key"],
            },
            ExpiresIn=3600,
        )
        result["download_url"] = url

    return _response(200, result)


def _response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body),
    }
