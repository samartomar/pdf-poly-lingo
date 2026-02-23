"""CI/CD Pipeline stack using CDK Pipelines."""

from aws_cdk import Stack, Stage
from aws_cdk import pipelines as pipelines
from constructs import Construct

from infrastructure.translation_service_stack import TranslationServiceStack


class PipelineStack(Stack):
    """Self-mutating pipeline that builds and deploys the translation service."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        github_owner: str = None,
        github_repo: str = None,
        github_branch: str = None,
        connection_arn: str = None,
        foundation=None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        connection_arn = connection_arn or self.node.try_get_context("connection_arn")
        github_owner = github_owner or self.node.try_get_context("github_owner") or "your-org"
        github_repo = github_repo or self.node.try_get_context("github_repo") or "pdf-poly-lingo"
        github_branch = github_branch or self.node.try_get_context("github_branch") or "main"

        repo = f"{github_owner}/{github_repo}"

        if connection_arn:
            source = pipelines.CodePipelineSource.connection(
                repo_string=repo,
                branch=github_branch,
                connection_arn=connection_arn,
            )
        else:
            source = pipelines.CodePipelineSource.git_hub(
                repo_string=repo,
                branch=github_branch,
            )

        synth = pipelines.ShellStep(
            "Synth",
            input=source,
            commands=[
                "npm install -g aws-cdk",
                "pip install -r requirements.txt",
                "cdk synth",
            ],
            primary_output_directory="cdk.out",
        )

        pipeline = pipelines.CodePipeline(
            self,
            "Pipeline",
            pipeline_name="pdf-poly-lingo",
            synth=synth,
        )

        pipeline.add_stage(TranslationServiceStage(self, "Prod"))


class TranslationServiceStage(Stage):
    """Deployable stage containing the translation service."""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        TranslationServiceStack(self, "TranslationService", **kwargs)
