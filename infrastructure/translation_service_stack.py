"""Translation service stack: S3, Lambda, Amazon Translate, API Gateway, IAM."""

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_iam as iam,
    aws_sns as sns,
    aws_dynamodb as dynamodb,
)
from constructs import Construct


class TranslationServiceStack(Stack):
    """AWS-native translation pipeline: upload -> Translate -> deliver."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ----- S3 Buckets -----
        input_bucket = s3.Bucket(
            self,
            "InputBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            cors=[
                s3.CorsRule(
                    allowed_methods=[
                        s3.HttpMethods.PUT,
                        s3.HttpMethods.GET,
                        s3.HttpMethods.HEAD,
                    ],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                    exposed_headers=["ETag"],
                ),
            ],
        )

        output_bucket = s3.Bucket(
            self,
            "OutputBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.HEAD],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                ),
            ],
        )

        temp_bucket = s3.Bucket(
            self,
            "TempBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        # ----- DynamoDB: job tracking -----
        jobs_table = dynamodb.Table(
            self,
            "JobsTable",
            partition_key=dynamodb.Attribute(name="request_id", type=dynamodb.AttributeType.STRING),
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ----- IAM Role for Amazon Translate -----
        translate_role = iam.Role(
            self,
            "TranslateServiceRole",
            assumed_by=iam.ServicePrincipal("translate.amazonaws.com"),
            description="Role for Amazon Translate to read input and write output S3",
        )
        input_bucket.grant_read(translate_role)
        output_bucket.grant_read_write(translate_role)
        temp_bucket.grant_read_write(translate_role)

        # ----- SNS Topic for completion notifications -----
        completion_topic = sns.Topic(
            self,
            "CompletionTopic",
            display_name="PDF Poly Lingo Translation Complete",
        )

        # ----- Lambda: Proxy upload (avoids S3 CORS, max 5MB) -----
        upload_proxy = _lambda.Function(
            self,
            "UploadProxy",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=_lambda.Code.from_asset("backend/upload_proxy"),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "INPUT_BUCKET": input_bucket.bucket_name,
                "REGION": self.region,
                "TABLE_NAME": jobs_table.table_name,
            },
        )
        input_bucket.grant_put(upload_proxy)
        jobs_table.grant_read_write_data(upload_proxy)
        upload_proxy.add_to_role_policy(
            iam.PolicyStatement(actions=["translate:TranslateDocument"], resources=["*"])
        )

        # ----- Lambda: Presigned URL -----
        presigned_handler = _lambda.Function(
            self,
            "PresignedUrlHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=_lambda.Code.from_asset("backend/presigned_url"),
            timeout=Duration.seconds(10),
            environment={
                "INPUT_BUCKET": input_bucket.bucket_name,
                "REGION": self.region,
            },
        )
        input_bucket.grant_put(presigned_handler)

        # ----- Lambda: S3 trigger -> Start Translate job -----
        translate_trigger = _lambda.Function(
            self,
            "TranslateTrigger",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=_lambda.Code.from_asset("backend/translate_trigger"),
            timeout=Duration.minutes(1),
            environment={
                "INPUT_BUCKET": input_bucket.bucket_name,
                "OUTPUT_BUCKET": output_bucket.bucket_name,
                "TEMP_BUCKET": temp_bucket.bucket_name,
                "TRANSLATE_ROLE_ARN": translate_role.role_arn,
                "COMPLETION_TOPIC_ARN": completion_topic.topic_arn,
                "TABLE_NAME": jobs_table.table_name,
            },
        )
        jobs_table.grant_read_write_data(translate_trigger)
        input_bucket.grant_read(translate_trigger)
        output_bucket.grant_read(translate_trigger)
        temp_bucket.grant_read_write(translate_trigger)
        translate_trigger.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "translate:StartTextTranslationJob",
                    "translate:DescribeTextTranslationJob",
                ],
                resources=["*"],
            )
        )
        translate_trigger.add_to_role_policy(
            iam.PolicyStatement(
                actions=["textract:DetectDocumentText", "textract:AnalyzeDocument"],
                resources=["*"],
            )
        )
        completion_topic.grant_publish(translate_trigger)

        input_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(translate_trigger),
            s3.NotificationKeyFilter(prefix="uploads/"),
        )

        # ----- Lambda: Output bucket notification -----
        notification_handler = _lambda.Function(
            self,
            "NotificationHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=_lambda.Code.from_asset("backend/notification_handler"),
            timeout=Duration.seconds(30),
            environment={
                "COMPLETION_TOPIC_ARN": completion_topic.topic_arn,
                "TABLE_NAME": jobs_table.table_name,
            },
        )
        jobs_table.grant_read_write_data(notification_handler)
        output_bucket.grant_read(notification_handler)
        completion_topic.grant_publish(notification_handler)
        output_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(notification_handler),
        )

        # ----- API Gateway -----
        api = apigw.RestApi(
            self,
            "TranslationApi",
            rest_api_name="PDF Poly Lingo Translation API",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization"],
            ),
        )
        # Proxy upload (no CORS issues, max 5MB)
        upload_resource = api.root.add_resource("upload")
        upload_resource.add_method("POST", apigw.LambdaIntegration(upload_proxy))

        presigned_resource = api.root.add_resource("presigned-url")
        presigned_resource.add_method("POST", apigw.LambdaIntegration(presigned_handler))

        # Status & download URL
        status_resource = api.root.add_resource("status")
        status_handler = _lambda.Function(
            self,
            "StatusHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=_lambda.Code.from_asset("backend/status_handler"),
            timeout=Duration.seconds(10),
            environment={
                "TABLE_NAME": jobs_table.table_name,
                "OUTPUT_BUCKET": output_bucket.bucket_name,
                "REGION": self.region,
            },
        )
        jobs_table.grant_read_data(status_handler)
        output_bucket.grant_read(status_handler)
        status_resource.add_method("GET", apigw.LambdaIntegration(status_handler))

        # ----- Outputs -----
        from aws_cdk import CfnOutput

        CfnOutput(self, "InputBucketName", value=input_bucket.bucket_name)
        CfnOutput(self, "OutputBucketName", value=output_bucket.bucket_name)
        CfnOutput(self, "ApiEndpoint", value=api.url)
