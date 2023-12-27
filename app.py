#!/usr/bin/env python3
import os
import aws_cdk as cdk

from stacks.iam_stack import IAMStack
from stacks.rds.rds import RDSStack
from stacks.infra.vpc_new import VPCStack
from stacks.infra.jumpbox import JumboxStack
from stacks.frontend.waf_admin_stack import WAFAdminStack
from stacks.frontend.waf_app_stack import WAFAppStack
from stacks.frontend.waf_identity_stack import WAFIdentityStack
from stacks.frontend.web_admin import WebAdminStack
from stacks.frontend.web_app import WebAppStack
from stacks.frontend.web_identity import WebIdentityStack
from stacks.cognito import CognitoUserPoolStack
from stacks.infra.acm_api_stack import AcmApiStack
from stacks.alb.waf_alb_stack import WafAlbStack
from stacks.alb.alb_stack import AlbStack
from stacks.infra.ssl_certificate_stack import SSLCertificateStack
from stacks.ecs.ecs_cluster_stack import ECSCluster
from stacks.ecs.api_svc_stack import ApiSvcStack
from stacks.ecs.account_svc_stack import AccountSvcStack
from stacks.sns_sqs.email_sns_sqs import EmailSNSSQS_Stack
from stacks.sns_sqs.api_sns_sqs import APISNSSQS_Stack
from stacks.sns_sqs.account_sns_sqs import AccountSNSSQS_Stack
from stacks.sns_sqs.api_to_account_sns_subcription import APISUBS_Stack
from stacks.sns_sqs.account_to_api_sns_subcription import AccountSUBS_Stack
from stacks.cloudtrail import CloudTrailStack
from helper import config

# CDK-NAG TESTING

from aws_cdk import Aspects

# Check Best practices based on AWS Solutions Security Matrix.
from cdk_nag import AwsSolutionsChecks

# Check for HIPAA Security compliance.
from cdk_nag import HIPAASecurityChecks

# Check for NIST 800-53 rev 4 compliance.
from cdk_nag import NIST80053R4Checks

# Check for NIST 800-53 rev 5 compliance.
from cdk_nag import NIST80053R5Checks

# Check for PCI DSS 3.2.1 compliance. Based on the PCI DSS 3.2.1 AWS operational best practices: https://docs.aws.amazon.com/config/latest/developerguide/operational-best-practices-for-pci-dss.html.
from cdk_nag import PCIDSS321Checks


app = cdk.App()
conf_app = config.Config(app.node.try_get_context("environment"))

website_main_domain = conf_app.get("web_domain")
############################################################################
#                                 IAM, Logging
#############################################################################

iam_stack = IAMStack(
    app,
    "iam-stack",
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
)


cloudtrail_stack = CloudTrailStack(
    app,
    "cloudtrail-stack",
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
)


############################################################################
#                                VPC CDK
#                      (VPC Components and Jumpbox)
#
#############################################################################


vpc_stack = VPCStack(
    app,
    "vpc-stack",
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
)
jumpbox = JumboxStack(
    app,
    "jumpbox",
    vpc=vpc_stack.vpc,
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
)


############################################################################
#          FRONT END CDK
#    (ACM SSL, WAF, ALB, Cognito, Website(web-admin, web-app, web-identity))
#
#############################################################################

cognito_stack = CognitoUserPoolStack(
    app,
    "cognito-stack",
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
)
# Create ACM
certificate_stack = SSLCertificateStack(app, "acm-stack", website_main_domain)
# web-admin
waf_admin_stack = WAFAdminStack(app, "waf-admin-stack")
waf_admin_stack.add_dependency(certificate_stack)
web_admin = WebAdminStack(
    app,
    "web-admin",
    tls_certificate=certificate_stack.certificate,
    waf_web_acl_id=waf_admin_stack.waf_web_arn,
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
)
web_admin.add_dependency(waf_admin_stack)

# web-app

waf_app_stack = WAFAppStack(app, "waf-app-stack")
waf_app_stack.add_dependency(certificate_stack)

web_app = WebAppStack(
    app,
    "web-app",
    tls_certificate=certificate_stack.certificate,
    waf_web_acl_id=waf_app_stack.waf_web_arn,
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
)
# web-identity

waf_identity_stack = WAFIdentityStack(app, "waf-identity-stack")
waf_identity_stack.add_dependency(certificate_stack)

web_identity = WebIdentityStack(
    app,
    "web-identity",
    tls_certificate=certificate_stack.certificate,
    waf_web_acl_id=waf_identity_stack.waf_web_arn,
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
)

############################################################################
#          BACKEND CDK
#    (ACM SSL, WAF, ALB, ....)
#
#############################################################################
waf_alb_stack = WafAlbStack(app, "waf-alb-stack")
acm_api_stack = AcmApiStack(
    app,
    "acm-api-stack",
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
    cross_region_references=True,
)

alb_stack = AlbStack(
    app,
    "alb-stack",
    vpc_stack.vpc,
    tls_certificate=certificate_stack.certificate,
    waf_web_acl_id=waf_alb_stack.waf_alb_id,
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
)

alb_stack.add_dependency(waf_alb_stack)
alb_stack.add_dependency(acm_api_stack)


ecs_cluster_stack = ECSCluster(
    app,
    "ecs-cluster-stack",
    vpc=vpc_stack.vpc,
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
)

api_service_stack = ApiSvcStack(
    app,
    "api-service-stack",
    vpc=vpc_stack.vpc,
    https_listener_arn=alb_stack.https_listener.attr_listener_arn,
    cluster=ecs_cluster_stack.cluster,
    private_sg=alb_stack.private_security_group.security_group_id,
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
)

account_service_stack = AccountSvcStack(
    app,
    "account-service-stack",
    vpc=vpc_stack.vpc,
    https_listener_arn=alb_stack.https_listener.attr_listener_arn,
    cluster=ecs_cluster_stack.cluster,
    private_sg=alb_stack.private_security_group.security_group_id,
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
)


############################################################################
#                    SNS, SQS
#############################################################################


email_snssqs_stack = EmailSNSSQS_Stack(
    app,
    "email-snssqs-stack",
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
    cross_region_references=True,
)

api_snssqs_stack = APISNSSQS_Stack(
    app,
    "api-snssqs-stack",
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
    cross_region_references=True,
)
account_snssqs_stack = AccountSNSSQS_Stack(
    app,
    "account-snssqs-stack",
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
    cross_region_references=True,
)
api_sns_subcriptions = APISUBS_Stack(
    app,
    "api-subs-stack",
    api_topic_arn=api_snssqs_stack.sns_topic.topic_arn,
    account_event_queue_arn=account_snssqs_stack.sqs_event_queue.queue_arn,
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
    cross_region_references=True,
)
account_sns_subcriptions = AccountSUBS_Stack(
    app,
    "account-subs-stack",
    account_topic_arn=account_snssqs_stack.sns_topic.topic_arn,
    api_event_queue_arn=api_snssqs_stack.sqs_event_queue.queue_arn,
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
    cross_region_references=True,
)

############################################################################
#          RDS POSTGRES CDK
#
#############################################################################
rds_stack = RDSStack(
    app,
    "rds-stack",
    vpc_stack.vpc,
    jump_sec_group=jumpbox.jump_sec_group,
    env=cdk.Environment(
        account=conf_app.get("account_id"), region=conf_app.get("region")
    ),
)

# Aspects.of(app).add(AwsSolutionsChecks())
# CHOOSE WHAT COMPLIANCE YOU WANT
# Aspects.of(app).add(HIPAASecurityChecks())
# Aspects.of(app).add(NIST80053R4Checks())
# Aspects.of(app).add(NIST80053R5Checks())
# Aspects.of(app).add(PCIDSS321Checks())

app.synth()
