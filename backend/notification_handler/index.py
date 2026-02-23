"""S3 trigger: notify when translated file lands in Output bucket."""

import json
import os

import boto3

SNS = boto3.client("sns")


def handler(event, context):
    """Publish to SNS when new object appears in Output bucket."""
    topic_arn = os.environ["COMPLETION_TOPIC_ARN"]

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        size = record["s3"]["object"].get("size", 0)

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
