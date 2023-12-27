"""Import Module."""
import aws_cdk as core
from aws_cdk import aws_iam as iam, Stack
from aws_cdk.aws_iam import User
from constructs import Construct
from helper import config


class IAMStack(Stack):
    """Class to create IAM components that need for application"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        conf = config.Config(self.node.try_get_context("environment"))
        tooling_aws_account_id = conf.get("tooling_aws_account_id")
        project_name = conf.get("project_name")
        stage = conf.get("stage")
        account_id = conf.get("account_id")
        region = conf.get("region")

        cross_account_codebuild_role = iam.Role(
            self,
            "Cross-Account-CodeBuild-Role",
            role_name="Cross-Account-CodeBuild-Role",
            assumed_by=iam.ArnPrincipal(f"arn:aws:iam::{tooling_aws_account_id}:root"),
        )
        policy_arns = [
            "arn:aws:iam::aws:policy/AmazonCognitoPowerUser",
            "arn:aws:iam::aws:policy/AmazonSSMReadOnlyAccess",
            "arn:aws:iam::aws:policy/AWSCloudFormationFullAccess",
            "arn:aws:iam::aws:policy/AWSLambda_FullAccess",
            "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryFullAccess",
            "arn:aws:iam::aws:policy/AmazonECS_FullAccess",
            "arn:aws:iam::aws:policy/IAMFullAccess",
            "arn:aws:iam::aws:policy/AmazonS3FullAccess",
            "arn:aws:iam::aws:policy/AmazonSSMReadOnlyAccess",
        ]

        index = 0
        for policy_arn in policy_arns:
            iam.Policy(
                self,
                f"CodeBuildPolicyAttachment-{index}",
                roles=[cross_account_codebuild_role],
                statements=[
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=["sts:AssumeRole"],
                        resources=[cross_account_codebuild_role.role_arn],
                    ),
                ],
            )
            index = index + 1

        cross_account_developer_role = iam.Role(
            self,
            "Cross-Account-developer-Role",
            role_name="Developer-Role",
            assumed_by=iam.ArnPrincipal(f"arn:aws:iam::{tooling_aws_account_id}:root"),
        )
        policy_arns = [
            "arn:aws:iam::aws:policy/AmazonCognitoPowerUser",
            "arn:aws:iam::aws:policy/AmazonSSMReadOnlyAccess",
            "arn:aws:iam::aws:policy/CloudWatchLogsReadOnlyAccess",
            "arn:aws:iam::aws:policy/IAMFullAccess",
            "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess",
        ]

        index = 0
        for policy_arn in policy_arns:
            iam.Policy(
                self,
                f"DevelopersPolicyAttachment-{index}",
                roles=[cross_account_developer_role],
                statements=[
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=["sts:AssumeRole"],
                        resources=[cross_account_developer_role.role_arn],
                    ),
                ],
            )
            index = index + 1

        # create a user cicd with permission to upload object, delete object, list object, list buckets, create cloudfront invalidation
        self.cicd_user = iam.User(
            self,
            "cicd-user",
            user_name="cicd",
        )

        CICD_STATEMENT_JSON = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "VisualEditor0",
                    "Effect": "Allow",
                    "Action": [
                        "cloudfront:ListInvalidations",
                        "cloudfront:ListDistributions",
                        "cloudfront:GetInvalidation",
                        "cloudfront:CreateInvalidation",
                    ],
                    "Resource": "*",
                },
                {
                    "Sid": "VisualEditor1",
                    "Effect": "Allow",
                    "Action": [
                        "s3:PutObjectAcl",
                        "s3:PutObject",
                        "s3:GetObjectAcl",
                        "s3:GetObject",
                        "s3:DeleteObject",
                        "s3:AbortMultipartUpload",
                    ],
                    "Resource": [
                        "arn:aws:s3:::*",
                    ],
                },
                {
                    "Sid": "VisualEditor2",
                    "Effect": "Allow",
                    "Action": ["s3:ListAllMyBuckets", "s3:ListBucket"],
                    "Resource": "*",
                },
            ],
        }
        cicd_policy_document = iam.PolicyDocument.from_json(CICD_STATEMENT_JSON)
        cicd_policy = iam.Policy(
            self,
            "cicd-policy",
            policy_name="cicd-policy",
            document=cicd_policy_document,
        )
        cicd_policy.attach_to_user(self.cicd_user)

        # ECS Task Role
        task_role = iam.Role(
            self,
            "ECSTaskExecutionRole-Fargate",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        task_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AmazonECSTaskExecutionRolePolicy"
            )
        )

        self.task_role_arn = task_role.role_arn
        core.CfnOutput(
            self, "Task-Role-Arn", value=self.task_role_arn, export_name="task-role-arn"
        )

        # Task Execution Role
        task_execution_role = iam.Role(
            self,
            "ECSExecutionRole ",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        task_execution_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonCognitoPowerUser")
        )
        task_execution_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSNSFullAccess")
        )
        task_execution_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3FullAccess")
        )
        task_execution_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSQSFullAccess")
        )
        task_execution_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMReadOnlyAccess")
        )
        self.task_execution_role_arn = task_execution_role.role_arn

        core.CfnOutput(
            self,
            "Task-Execution-Role-Arn",
            value=self.task_execution_role_arn,
            export_name="task-execution-role-arn",
        )

        # CodeDeploy Role
        code_deploy_role = iam.Role(
            self,
            "CodeDeployRole",
            assumed_by=iam.ServicePrincipal("codedeploy.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AWSCodeDeployRoleForECS"
                )
            ],
        )
        self.code_deploy_role_arn = code_deploy_role.role_arn

        core.CfnOutput(
            self,
            "CodeDeploy-Role-Arn",
            value=self.code_deploy_role_arn,
            export_name="codedeploy-role-arn",
        )

        self.code_pipeline_role = iam.Role(
            self,
            "CodePipelineRole",
            assumed_by=iam.ServicePrincipal("codepipeline.amazonaws.com"),
        )

        CODEPIPELINE_STATEMENT_JSON = {
            "Statement": [
                {
                    "Action": ["iam:PassRole"],
                    "Resource": "*",
                    "Effect": "Allow",
                    "Condition": {
                        "StringEqualsIfExists": {
                            "iam:PassedToService": [
                                "cloudformation.amazonaws.com",
                                "elasticbeanstalk.amazonaws.com",
                                "ec2.amazonaws.com",
                                "ecs-tasks.amazonaws.com",
                            ]
                        }
                    },
                },
                {
                    "Action": [
                        "codedeploy:CreateDeployment",
                        "codedeploy:GetApplication",
                        "codedeploy:GetApplicationRevision",
                        "codedeploy:GetDeployment",
                        "codedeploy:GetDeploymentConfig",
                        "codedeploy:RegisterApplicationRevision",
                    ],
                    "Resource": "*",
                    "Effect": "Allow",
                },
                {
                    "Action": ["codestar-connections:UseConnection"],
                    "Resource": "*",
                    "Effect": "Allow",
                },
                {
                    "Action": [
                        "ec2:*",
                        "elasticloadbalancing:*",
                        "cloudwatch:*",
                        "s3:*",
                        "sns:*",
                        "cloudformation:*",
                        "ecs:*",
                    ],
                    "Resource": "*",
                    "Effect": "Allow",
                },
                {
                    "Action": ["lambda:InvokeFunction", "lambda:ListFunctions"],
                    "Resource": "*",
                    "Effect": "Allow",
                },
                {
                    "Action": [
                        "cloudformation:CreateStack",
                        "cloudformation:DeleteStack",
                        "cloudformation:DescribeStacks",
                        "cloudformation:UpdateStack",
                        "cloudformation:CreateChangeSet",
                        "cloudformation:DeleteChangeSet",
                        "cloudformation:DescribeChangeSet",
                        "cloudformation:ExecuteChangeSet",
                        "cloudformation:SetStackPolicy",
                        "cloudformation:ValidateTemplate",
                    ],
                    "Resource": "*",
                    "Effect": "Allow",
                },
                {
                    "Effect": "Allow",
                    "Action": ["cloudformation:ValidateTemplate"],
                    "Resource": "*",
                },
                {"Effect": "Allow", "Action": ["ecr:DescribeImages"], "Resource": "*"},
                {
                    "Effect": "Allow",
                    "Action": [
                        "states:DescribeExecution",
                        "states:DescribeStateMachine",
                        "states:StartExecution",
                    ],
                    "Resource": "*",
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "appconfig:StartDeployment",
                        "appconfig:StopDeployment",
                        "appconfig:GetDeployment",
                    ],
                    "Resource": "*",
                },
            ],
            "Version": "2012-10-17",
        }
        codepipeline_policy_document = iam.PolicyDocument.from_json(
            CODEPIPELINE_STATEMENT_JSON
        )
        codepipeline_policy = iam.Policy(
            self,
            "codepipeline-policy",
            policy_name="codepipeline-policy",
            document=codepipeline_policy_document,
        )

        codepipeline_policy.attach_to_role(self.code_pipeline_role)

        core.CfnOutput(
            self,
            "CodePipeline-Role-Arn",
            value=self.code_pipeline_role.role_arn,
            export_name="codepipeline-role-arn",
        )

        self.cloud_trail_role = iam.Role(
            self,
            "CloudTrail-Role",
            role_name=f"cloudtrail-logs-management-cloudwatch-role-{stage}",
            assumed_by=iam.ServicePrincipal("cloudtrail.amazonaws.com"),
        )

        CLOUDTRAIL_STATEMENT_JSON = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AWSCloudTrailCreateLogStream",
                    "Effect": "Allow",
                    "Action": ["logs:CreateLogStream"],
                    "Resource": [
                        f"arn:aws:logs:{region}:{account_id}:log-group:{project_name}-aws-cloudtrail-logs-management-{stage}:*"
                    ],
                },
                {
                    "Sid": "AWSCloudTrailPutLogEvents20141101",
                    "Effect": "Allow",
                    "Action": ["logs:PutLogEvents"],
                    "Resource": [
                        f"arn:aws:logs:{region}:{account_id}:log-group:{project_name}-aws-cloudtrail-logs-management-{stage}:*"
                    ],
                },
            ],
        }

        cloudtrail_policy_document = iam.PolicyDocument.from_json(
            CLOUDTRAIL_STATEMENT_JSON
        )
        cloudtrail_policy = iam.Policy(
            self,
            "CloudTrail-cloudWatch-policy",
            policy_name="CloudTrail-cloudWatch-policy",
            document=cloudtrail_policy_document,
        )

        cloudtrail_policy.attach_to_role(self.cloud_trail_role)

        core.CfnOutput(
            self,
            "CloudTrail-Role-Arn",
            value=self.cloud_trail_role.role_arn,
            export_name="cloudtrail-role-arn",
        )
