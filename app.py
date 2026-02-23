#!/usr/bin/env python3
"""PDF Poly Lingo - CDK Application.

Hosts CI/CD pipeline and translation service built on AWS:
- S3 (Input/Output buckets)
- Lambda (presigned URL, Translate trigger, completion notification)
- Amazon Translate (async batch for HTML/text; PDF via Textract preprocessing)
- API Gateway, SNS
"""

import aws_cdk as cdk
from infrastructure.pipeline_stack import PipelineStack
from infrastructure.translation_service_stack import TranslationServiceStack

app = cdk.App()

env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "us-west-2",
)

# Pipeline stack - requires GitHub connection and repo details
PipelineStack(
    app,
    "PipelineStack",
    github_owner="samartomar",
    github_repo="py-poc",
    github_branch="gap-hardening-01",
    connection_arn="arn:aws:codeconnections:us-west-2:674763518102:connection/a4712769-a210-4d9a-9eed-8f244e3cc48d",
    env=env,
    description="CI/CD pipeline for PDF Poly Lingo translation service",
)

# Standalone service stack for direct deploy (without pipeline)
deploy_direct = app.node.try_get_context("deploy_direct")
if deploy_direct:
    TranslationServiceStack(
        app,
        "TranslationService",
        env=env,
        description="Translation service (direct deploy)",
    )

app.synth()
