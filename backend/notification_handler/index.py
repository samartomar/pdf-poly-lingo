"""S3 trigger: notify when translated file lands in Output bucket."""

import json
import os
import re

import boto3

SNS = boto3.client("sns")
DYNAMO = boto3.resource("dynamodb")


def handler(event, context):
    """Publish to SNS and update DynamoDB when new object appears in Output bucket."""
    topic_arn = os.environ["COMPLETION_TOPIC_ARN"]
    table_name = os.environ.get("TABLE_NAME")

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        size = record["s3"]["object"].get("size", 0)

        # Skip auxiliary metadata and details subfolder - return only the translated document
        if (
            key.endswith(".auxiliary-translation-details.json")
            or "/details/" in key
        ):
            continue

        # Extract job_id from path: .../account-TranslateText-jobId/...
        match = re.search(r"TranslateText-([^/]+)", key)
        if match and table_name:
            job_id = match.group(1)
            table = DYNAMO.Table(table_name)
            # Find item by job_id (scan or GSI)
            resp = table.scan(FilterExpression="job_id = :jid", ExpressionAttributeValues={":jid": job_id})
            for item in resp.get("Items", []):
                table.update_item(
                    Key={"request_id": item["request_id"]},
                    UpdateExpression="SET #s = :s, output_key = :k, output_bucket = :b",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":s": "complete",
                        ":k": key,
                        ":b": bucket,
                    },
                )
                break

        SNS.publish(
            TopicArn=topic_arn,
            Subject="Translation complete: PDF Poly Lingo",
            Message=json.dumps({
                "event": "translation_complete",
                "bucket": bucket,
                "key": key,
                "size": size,
            }),
        )
    return {"statusCode": 200}
