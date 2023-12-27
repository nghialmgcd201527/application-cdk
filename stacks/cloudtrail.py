"""Import necessary CDK modules."""
import aws_cdk as core
from constructs import Construct
from aws_cdk import (
    Stack,
    aws_cloudtrail as trail,
    aws_logs as logs,
    aws_s3 as s3,
    aws_iam as iam,
)
from helper import config


class CloudTrailStack(Stack):
    """Class to create CloudTrai"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Declare vars
        conf = config.Config(self.node.try_get_context("environment"))
        project_name = conf.get("project_name")
        stage = conf.get("stage")
        account_id = conf.get("account_id")
        region = conf.get("region")

        trail_log_group = logs.LogGroup(
            self,
            "CloudTrailLogGroup",
            log_group_name=f"{project_name}-aws-cloudtrail-logs-management-{stage}",
        )

        cloudtrail_role_arn = core.Fn.import_value("cloudtrail-role-arn")

        # cloudtrail_s3_bucket_name = (
        #     f"{project_name}-aws-cloudtrail-logs-management-{stage}".lower
        # )

        cloudtrail_s3_bucket = s3.Bucket(
            self,
            "CloudTrail-S3-Bucket",
            bucket_name=f"{project_name}-aws-cloudtrail-logs-management-{stage}",
        )

        # Define the IAM Policy Statements
        cloudtrail_s3_statement_1 = iam.PolicyStatement(
            sid="AWSCloudTrailAclCheck",
            effect=iam.Effect.ALLOW,
            principals=[iam.ServicePrincipal("cloudtrail.amazonaws.com")],
            actions=["s3:GetBucketAcl"],
            resources=[cloudtrail_s3_bucket.bucket_arn],
            # conditions={
            #     "StringEquals": {
            #         "AWS:SourceArn": f"arn:aws:cloudtrail:{region}:{account_id}:trail/{project_name}-cloudtrail-management-{stage}.trail"
            #     }
            # },
        )
        cloudtrail_s3_statement_2 = iam.PolicyStatement(
            sid="AWSCloudTrailWrite",
            effect=iam.Effect.ALLOW,
            principals=[iam.ServicePrincipal("cloudtrail.amazonaws.com")],
            actions=["s3:PutObject"],
            resources=[f"{cloudtrail_s3_bucket.bucket_arn}/AWSLogs/{account_id}/*"],
            conditions={
                "StringEquals": {
                    "s3:x-amz-acl": "bucket-owner-full-control",
                    #   "AWS:SourceArn": f"arn:aws:cloudtrail:{region}:{account_id}:trail/{project_name}-cloudtrail-management-{stage}.trail",
                }
            },
        )

        cloudtrail_s3_bucket.add_to_resource_policy(cloudtrail_s3_statement_1)
        cloudtrail_s3_bucket.add_to_resource_policy(cloudtrail_s3_statement_2)

        trail.CfnTrail(
            self,
            f"{project_name}-CloudTrail",
            trail_name=f"{project_name}-cloudtrail-management-{stage}",
            s3_bucket_name=cloudtrail_s3_bucket.bucket_name,
            cloud_watch_logs_log_group_arn=trail_log_group.log_group_arn,
            cloud_watch_logs_role_arn=cloudtrail_role_arn,
            is_logging=True,
            include_global_service_events=False,
            event_selectors=[
                trail.CfnTrail.EventSelectorProperty(
                    read_write_type="All",
                    include_management_events=True,
                    exclude_management_event_sources=["rdsdata.amazonaws.com"],
                )
            ],
        )
