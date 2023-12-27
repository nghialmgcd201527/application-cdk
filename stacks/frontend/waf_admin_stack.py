"""Module Import."""
import os
from constructs import Construct
from aws_cdk import (
    Stack,
    aws_wafv2 as waf,
    aws_logs as logs,
    Environment,
)
import aws_cdk as core
from helper import config


class WAFAdminStack(Stack):
    """Class to create WAF for WebAdmin Stack"""

    def __init__(self, scope: Construct, construct_id, **kwargs) -> None:
        cdk_environment = Environment(
            region="us-east-1", account=os.getenv("CDK_DEFAULT_ACCOUNT")
        )
        super().__init__(
            scope,
            construct_id,
            env=cdk_environment,
            cross_region_references=True,
            **kwargs,
        )

        conf = config.Config(self.node.try_get_context("environment"))
        project_name = conf.get("project_name")
        stage = conf.get("stage")
        bucket_name = f"{project_name}-web-admin"

        basic_rule = waf.CfnWebACL.RuleProperty(
            name="AWS-AWSManagedRulesCommonRuleSet",
            priority=3,
            statement=waf.CfnWebACL.StatementProperty(
                managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                    name="AWSManagedRulesCommonRuleSet", vendor_name="AWS"
                )
            ),
            override_action=waf.CfnWebACL.OverrideActionProperty(count={}),
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=False,
                metric_name="AWS-AWSManagedRulesCommonRuleSet",
                sampled_requests_enabled=True,
            ),
        )

        basic_rule_1 = waf.CfnWebACL.RuleProperty(
            name="AWS-AWSManagedRulesAnonymousIpList",
            priority=0,
            statement=waf.CfnWebACL.StatementProperty(
                managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                    name="AWSManagedRulesAnonymousIpList", vendor_name="AWS"
                )
            ),
            override_action=waf.CfnWebACL.OverrideActionProperty(count={}),
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=False,
                metric_name="AWS-AWSManagedRulesAnonymousIpList",
                sampled_requests_enabled=True,
            ),
        )

        basic_rule_2 = waf.CfnWebACL.RuleProperty(
            name="AWS-AWSManagedRulesAmazonIpReputationList",
            priority=1,
            statement=waf.CfnWebACL.StatementProperty(
                managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                    name="AWSManagedRulesAmazonIpReputationList", vendor_name="AWS"
                )
            ),
            override_action=waf.CfnWebACL.OverrideActionProperty(count={}),
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=False,
                metric_name="AWS-AWSManagedRulesAmazonIpReputationList",
                sampled_requests_enabled=True,
            ),
        )

        basic_rule_3 = waf.CfnWebACL.RuleProperty(
            name="AWS-AWSManagedRulesAdminProtectionRuleSet",
            priority=2,
            statement=waf.CfnWebACL.StatementProperty(
                managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                    name="AWSManagedRulesAdminProtectionRuleSet", vendor_name="AWS"
                )
            ),
            override_action=waf.CfnWebACL.OverrideActionProperty(count={}),
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=False,
                metric_name="AWS-AWSManagedRulesAdminProtectionRuleSet",
                sampled_requests_enabled=True,
            ),
        )

        basic_rule_4 = waf.CfnWebACL.RuleProperty(
            name="AWS-AWSManagedRulesKnownBadInputsRuleSet",
            priority=4,
            statement=waf.CfnWebACL.StatementProperty(
                managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                    name="AWSManagedRulesKnownBadInputsRuleSet", vendor_name="AWS"
                )
            ),
            override_action=waf.CfnWebACL.OverrideActionProperty(count={}),
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=False,
                metric_name="AWS-AWSManagedRulesKnownBadInputsRuleSet",
                sampled_requests_enabled=True,
            ),
        )

        web_acl = waf.CfnWebACL(
            self,
            "web-acl-id",
            default_action=waf.CfnWebACL.DefaultActionProperty(allow={}),
            scope="CLOUDFRONT",
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=False,
                metric_name=project_name + "-" + stage,
                sampled_requests_enabled=True,
            ),
            name=project_name + "-" + stage + "web-admin-acl",
            rules=[basic_rule, basic_rule_1, basic_rule_2, basic_rule_3, basic_rule_4],
        )

        waf_log = logs.LogGroup(
            self,
            f"aws-waf-logs-{bucket_name}",
            log_group_name=f"aws-waf-logs-{bucket_name}",
        )

        waf.CfnLoggingConfiguration(
            self,
            f"aws-waf-logging-{bucket_name}-configuration",
            log_destination_configs=[waf_log.log_group_arn],
            resource_arn=web_acl.attr_arn,
        )

        self.waf_web_arn = web_acl.attr_arn

        core.CfnOutput(
            self, "waf-webacl-arn", value=self.waf_web_arn, export_name="waf-webacl-arn"
        )

        # ssm.StringParameter(self, 'webacl-id-ssm',
        #     parameter_name='/'+env_name+'/webacl-id',
        #     string_value=web_acl.attr_id
