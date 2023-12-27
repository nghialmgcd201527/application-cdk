from constructs import Construct
from aws_cdk import (
    Stack,
    aws_wafv2 as waf,
    RemovalPolicy,
    Tags,
    Environment,
)
import os
import aws_cdk as core
from helper import config


def make_rules(list_of_rules={}):
    rules = list()
    for r in list_of_rules:
        rule = waf.CfnWebACL.RuleProperty(
            name=r["name"],
            priority=r["priority"],
            override_action=waf.CfnWebACL.OverrideActionProperty(none={}),
            statement=waf.CfnWebACL.StatementProperty(
                managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                    name=r["name"], vendor_name="AWS", excluded_rules=[]
                )  # managed_rule_group_statement
            ),  # statement
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name=r["name"],
                sampled_requests_enabled=True,
            ),  # visibility_config
        )  # wafv2.CfnWebACL.RuleProperty
        rules.append(rule)

    ##
    # Allowed country list
    ##
    ruleGeoMatch = waf.CfnWebACL.RuleProperty(
        name="GeoMatch",
        priority=0,
        action=waf.CfnWebACL.RuleActionProperty(
            block={}  # To disable, change to *count*
        ),
        statement=waf.CfnWebACL.StatementProperty(
            not_statement=waf.CfnWebACL.NotStatementProperty(
                statement=waf.CfnWebACL.StatementProperty(
                    geo_match_statement=waf.CfnWebACL.GeoMatchStatementProperty(
                        ##
                        # block connection if source not in the below country list
                        ##
                        country_codes=[
                            "US",  # USA
                            "VN",  # Vietnam
                            "CA"
                            # "BR",  # Brazil
                            # "CL",  # Chile
                            # "CO",  # Colombia
                            # "EC",  # Ecuador
                            # "FK",  # Falkland Islands
                            # "GF",  # French Guiana
                            # "GY",  # Guiana
                            # "GY",  # Guyana
                            # "PY",  # Paraguay
                            # "PE",  # Peru
                            # "SR",  # Suriname
                            # "UY",  # Uruguay
                            # "VE",  # Venezuela
                        ]  # country_codes
                    )  # geo_match_statement
                )  # statement
            )  # not_statement
        ),  # statement
        visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
            cloud_watch_metrics_enabled=True,
            metric_name="GeoMatch",
            sampled_requests_enabled=True,
        ),  # visibility_config
    )  # GeoMatch
    rules.append(ruleGeoMatch)

    ##
    # The rate limit is the maximum number of requests from a
    # single IP address that are allowed in a five-minute period.
    # This value is continually evaluated,
    # and requests will be blocked once this limit is reached.
    # The IP address is automatically unblocked after it falls below the limit.
    ##
    ruleLimitRequests1000 = waf.CfnWebACL.RuleProperty(
        name="LimitRequests1000",
        priority=1,
        action=waf.CfnWebACL.RuleActionProperty(
            block={}  # To disable, change to *count*
        ),  # action
        statement=waf.CfnWebACL.StatementProperty(
            rate_based_statement=waf.CfnWebACL.RateBasedStatementProperty(
                limit=1000, aggregate_key_type="IP"
            )  # rate_based_statement
        ),  # statement
        visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
            cloud_watch_metrics_enabled=True,
            metric_name="LimitRequests1000",
            sampled_requests_enabled=True,
        ),
    )  # limit requests to 100
    rules.append(ruleLimitRequests1000)

    return rules


class WafAlbStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        removal_policy: RemovalPolicy = RemovalPolicy.RETAIN,
        **kwargs
    ) -> None:
        cdk_environment = Environment(
            region="us-east-1", account=os.getenv("CDK_DEFAULT_ACCOUNT")
        )
        super().__init__(
            scope,
            construct_id,
            env=cdk_environment,
            **kwargs,
            cross_region_references=True
        )

        conf = config.Config(self.node.try_get_context("environment"))
        # WAF FOR CLOUDFRONT ALB
        ##
        # List available Managed Rule Groups using AWS CLI
        # aws wafv2 list-available-managed-rule-groups --scope CLOUDFRONT
        ##
        managed_rules = [
            {
                "name": "AWSManagedRulesCommonRuleSet",
                "priority": 10,
                "override_action": "none",
                "excluded_rules": [],
            },
            {
                "name": "AWSManagedRulesAmazonIpReputationList",
                "priority": 20,
                "override_action": "none",
                "excluded_rules": [],
            },
            {
                "name": "AWSManagedRulesKnownBadInputsRuleSet",
                "priority": 30,
                "override_action": "none",
                "excluded_rules": [],
            },
            {
                "name": "AWSManagedRulesSQLiRuleSet",
                "priority": 40,
                "override_action": "none",
                "excluded_rules": [],
            },
            {
                "name": "AWSManagedRulesLinuxRuleSet",
                "priority": 50,
                "override_action": "none",
                "excluded_rules": [],
            },
            {
                "name": "AWSManagedRulesUnixRuleSet",
                "priority": 60,
                "override_action": "none",
                "excluded_rules": [],
            },
        ]

        self.waf_alb = waf.CfnWebACL(
            self,
            "WebACL",
            default_action=waf.CfnWebACL.DefaultActionProperty(
                allow=waf.CfnWebACL.AllowActionProperty(), block=None
            ),
            ##
            # The scope of this Web ACL.
            # Valid options: CLOUDFRONT, REGIONAL.
            # For CLOUDFRONT, you must create your WAFv2 resources
            # in the US East (N. Virginia) Region, us-east-1
            # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-wafv2-webacl.html#cfn-wafv2-webacl-scope
            ##
            scope="CLOUDFRONT",
            ##
            # Defines and enables Amazon CloudWatch metrics and web request sample collection.
            ##
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="waf-cloudfront",
                sampled_requests_enabled=True,
            ),
            description="WAFv2 ACL for CloudFront",
            # name="waf-cloudfront",
            rules=make_rules(managed_rules),
        )
        self.waf_alb.apply_removal_policy(removal_policy)

        self.waf_alb_id = self.waf_alb.attr_id

        Tags.of(self.waf_alb).add("Name", "waf-cloudfront-alb", priority=300)
        Tags.of(self.waf_alb).add("Purpose", "WAF for CloudFront ALB", priority=300)
        Tags.of(self.waf_alb).add("CreatedBy", "CDK", priority=300)

        core.CfnOutput(
            self,
            "WafWebAclArn",
            value=self.waf_alb.attr_arn,
            description="The Amazon Resource Name (ARN) of the web ACL.",
            export_name="api-acl-arn",
        )
        core.CfnOutput(
            self,
            "WafWebAclId",
            value=self.waf_alb.attr_id,
            description="The ID of the web ACL.",
            export_name="api-acl-id",
        )
        core.CfnOutput(
            self,
            "WafWebAclName",
            value=str(self.waf_alb.name),
            description="The name of the web ACL.",
            export_name="api-acl-name",
        )
