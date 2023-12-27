"""Module Import"""
import aws_cdk as core
from constructs import Construct
from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_route53 as r53,
    RemovalPolicy,
)
from aws_cdk.aws_certificatemanager import Certificate
from helper import config


class WebAppStack(Stack):
    """Class to create WebApp"""

    def __init__(
        self,
        scope: Construct,
        construct_id,
        tls_certificate: Certificate,
        waf_web_acl_id: str,
        **kwargs,
    ) -> None:
        super().__init__(
            scope,
            construct_id,
            cross_region_references=True,
            **kwargs,
        )

        # create an S3 bucket
        conf = config.Config(self.node.try_get_context("environment"))
        environment = conf.get("environment")
        project_name = conf.get("project_name")
        bucket_name = f"{project_name}-web-app-{environment}"
        web_app_domain = conf.get("web_domain")
        account_id = conf.get("account_id")
        # try:
        #     self.logs_bucket = s3.Bucket.from_bucket_name(
        #         self, f"{project_name}-{environment}-s3-access-logs"
        #     )
        # except:
        #     self.logs_bucket = s3.Bucket(
        #         self,
        #         f"{project_name}-{environment}-s3-access-logs",
        #         bucket_name=f"{project_name}-{environment}-s3-access-logs",
        #         encryption=s3.BucketEncryption.S3_MANAGED,
        #         block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        #         enforce_ssl=True,
        #         removal_policy=RemovalPolicy.DESTROY,
        #         versioned=True,
        #         auto_delete_objects=True,
        #     )
        my_hosted_zone = r53.HostedZone.from_lookup(
            self, f"{web_app_domain}", domain_name=f"{web_app_domain}"
        )
        web_site_bucket = s3.Bucket(
            self,
            bucket_name,
            # server_access_logs_bucket=s3.Bucket.from_bucket_name(
            #     self, f"{bucket_name}-AccessLogsBucket", self.logs_bucket.bucket_name
            # ),
            # server_access_logs_prefix=f"access_logs/{bucket_name}",
            versioned=False,
            cors=[
                s3.CorsRule(
                    allowed_headers=["*"],
                    allowed_methods=[
                        s3.HttpMethods.PUT,
                        s3.HttpMethods.POST,
                        s3.HttpMethods.GET,
                        s3.HttpMethods.DELETE,
                    ],
                    allowed_origins=["*"],
                    exposed_headers=["ETag"],
                    max_age=3000,
                )
            ],
            removal_policy=RemovalPolicy.DESTROY,
        )

        # create an OAC
        web_oac_config = (
            cloudfront.CfnOriginAccessControl.OriginAccessControlConfigProperty(
                name=f"{bucket_name}-OAC-Config",
                origin_access_control_origin_type="s3",
                signing_behavior="always",
                signing_protocol="sigv4",
            )
        )

        web_oac = cloudfront.CfnOriginAccessControl(
            self, f"{bucket_name}-OAC", origin_access_control_config=web_oac_config
        )

        # create a distribution
        web_distribution = cloudfront.Distribution(
            self,
            f"{bucket_name}-Distribution",
            default_behavior=cloudfront.BehaviorOptions(
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
                cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD_OPTIONS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                compress=True,
                origin_request_policy=cloudfront.OriginRequestPolicy.CORS_S3_ORIGIN,
                response_headers_policy=cloudfront.ResponseHeadersPolicy.CORS_ALLOW_ALL_ORIGINS,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                origin=origins.S3Origin(web_site_bucket),
            ),
            domain_names=[web_app_domain],
            default_root_object="index.html",
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
            web_acl_id=waf_web_acl_id,
            certificate=tls_certificate,
        )

        web_oac_bucket_statement = iam.PolicyStatement(
            sid="AllowS3OACAccess",
            effect=iam.Effect.ALLOW,
            principals=[iam.ServicePrincipal("cloudfront.amazonaws.com")],
            actions=["s3:GetObject", "s3:PutObject"],
            resources=[f"arn:aws:s3:::{web_site_bucket.bucket_name}/*"],
            conditions={
                "StringEquals": {
                    "aws:sourceArn": f"arn:aws:cloudfront::{self.account}:distribution/{web_distribution.distribution_id}",
                }
            },
        )
        user_statement = iam.PolicyStatement(
            sid="AllowCICDPutGet",
            effect=iam.Effect.ALLOW,
            principals=[iam.ArnPrincipal(f"arn:aws:iam::{account_id}:user/cicd")],
            actions=[
                "s3:PutObjectAcl",
                "s3:PutObject",
                "s3:GetObjectAcl",
                "s3:GetObject",
                "s3:DeleteObject",
                "s3:AbortMultipartUpload",
            ],
            resources=[f"arn:aws:s3:::{web_site_bucket.bucket_name}/*"],
        )

        list_bucket_statement = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            principals=[iam.ArnPrincipal(f"arn:aws:iam::{account_id}:user/cicd")],
            actions=["s3:ListBucket"],
            resources=[f"arn:aws:s3:::{web_site_bucket.bucket_name}"],
        )

        # add the above S3 bucket policy to the "demo_site_bucket"
        web_site_bucket.add_to_resource_policy(web_oac_bucket_statement)
        web_site_bucket.add_to_resource_policy(user_statement)
        web_site_bucket.add_to_resource_policy(list_bucket_statement)

        # clean-up the OAI reference and associate the OAC with the cloudfront distribution
        # query the site bucket policy as a document
        bucket_policy = web_site_bucket.policy
        bucket_policy_document = bucket_policy.document

        # remove the CloudFront Origin Access Identity permission from the bucket policy
        if isinstance(bucket_policy_document, iam.PolicyDocument):
            bucket_policy_document_json = bucket_policy_document.to_json()
            # create an updated policy without the OAI reference
            bucket_policy_updated_json = {"Version": "2012-10-17", "Statement": []}
            for statement in bucket_policy_document_json["Statement"]:
                if "CanonicalUser" not in statement["Principal"]:
                    bucket_policy_updated_json["Statement"].append(statement)

            # apply the updated bucket policy to the bucket
        bucket_policy_override = web_site_bucket.node.find_child(
            "Policy"
        ).node.default_child
        bucket_policy_override.add_override(
            "Properties.PolicyDocument", bucket_policy_updated_json
        )

        # remove the created OAI reference (S3 Origin property) for the distribution
        all_distribution_props = web_distribution.node.find_all()
        for child in all_distribution_props:
            if child.node.id == "S3Origin":
                child.node.try_remove_child("Resource")

            # associate the created OAC with the distribution
        distribution_props = web_distribution.node.default_child
        distribution_props.add_override(
            "Properties.DistributionConfig.Origins.0.S3OriginConfig.OriginAccessIdentity",
            "",
        )
        distribution_props.add_property_override(
            "DistributionConfig.Origins.0.OriginAccessControlId", web_oac.ref
        )

        r53.CfnRecordSetGroup(
            self,
            "web-app-A-Record",
            record_sets=[
                r53.CfnRecordSetGroup.RecordSetProperty(
                    name=web_app_domain,
                    type="A",
                    alias_target=r53.CfnRecordSetGroup.AliasTargetProperty(
                        hosted_zone_id="Z2FDTNDATAQYW2",  # for china region Z3RFFRIM2A3IF5
                        dns_name=web_distribution.distribution_domain_name,
                    ),
                )
            ],
            hosted_zone_id=my_hosted_zone.hosted_zone_id,
        )

        core.CfnOutput(
            self,
            "distribution_url",
            value=web_distribution.domain_name,
            export_name=f"{project_name}-cfn-web-app-url",
        )

        core.CfnOutput(
            self,
            "distribution_id",
            value=web_distribution.distribution_id,
            export_name=f"{project_name}-cfn-web-app-id",
        )

        core.CfnOutput(
            self,
            "bucket_arn",
            value=web_site_bucket.bucket_arn,
            export_name=f"{project_name}-bucket-web-app-arn",
        )
