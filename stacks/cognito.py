# Import necessary CDK modules
import aws_cdk as core
from constructs import Construct
from aws_cdk import (
    aws_wafv2 as waf,
    Stack,
    aws_cognito as cognito,
)
from helper import config


class CognitoUserPoolStack(Stack):
    """Class to create Cognito"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Declare vars
        conf = config.Config(self.node.try_get_context("environment"))
        project_name = conf.get("project_name")
        stage = conf.get("stage")
        pool_name = f"{project_name}-{stage}-userpool"
        app_client_name = f"{project_name}-{stage}-userpoolappclient"
        # create userpool
        user_pool = cognito.UserPool(
            self,
            id="aBcXyZ",  # any value
            user_pool_name=pool_name,
            auto_verify=cognito.AutoVerifiedAttrs(email=True, phone=False),
            sign_in_aliases=cognito.SignInAliases(username=True),
            sign_in_case_sensitive=False,
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            deletion_protection=True,
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
                given_name=cognito.StandardAttribute(required=True, mutable=True),
                family_name=cognito.StandardAttribute(required=True, mutable=True),
                address=cognito.StandardAttribute(required=False, mutable=True),
                birthdate=cognito.StandardAttribute(required=False, mutable=True),
                gender=cognito.StandardAttribute(required=False, mutable=True),
                locale=cognito.StandardAttribute(required=False, mutable=True),
                nickname=cognito.StandardAttribute(required=False, mutable=True),
                phone_number=cognito.StandardAttribute(required=False, mutable=True),
                preferred_username=cognito.StandardAttribute(
                    required=False, mutable=True
                ),
                website=cognito.StandardAttribute(required=False, mutable=True),
            ),
            custom_attributes={
                "city": cognito.StringAttribute(min_len=1, max_len=256, mutable=True),
                "state": cognito.StringAttribute(min_len=1, max_len=256, mutable=True),
                "user_type": cognito.StringAttribute(
                    min_len=1, max_len=256, mutable=True
                ),
                "zip_code": cognito.StringAttribute(
                    min_len=1, max_len=256, mutable=True
                ),
            },
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
            ),
            mfa=cognito.Mfa.OFF,
            # email_settings = cognito.EmailSettings()
        )
        app_client = cognito.CfnUserPoolClient(
            self,
            id=app_client_name,
            user_pool_id=user_pool.user_pool_id,
            access_token_validity=60,
            id_token_validity=60,
            generate_secret=False,
            explicit_auth_flows=[
                "ALLOW_ADMIN_USER_PASSWORD_AUTH",
                "ALLOW_CUSTOM_AUTH",
                "ALLOW_REFRESH_TOKEN_AUTH",
                "ALLOW_USER_PASSWORD_AUTH",
                "ALLOW_USER_SRP_AUTH",
            ],
            token_validity_units=cognito.CfnUserPoolClient.TokenValidityUnitsProperty(
                access_token="minutes", id_token="minutes", refresh_token="days"
            ),
        )

        # Create WAF Web ACL
        waf_web_acl = waf.CfnWebACL(
            self,
            "CognitoWAFWebACL",
            scope="REGIONAL",
            default_action=waf.CfnWebACL.DefaultActionProperty(allow={}),
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="CognitoWebACL",
                sampled_requests_enabled=True
            )
        )

        waf_association = waf.CfnWebACLAssociation(
            self,
            "CognitoWAFAssociation",
            resource_arn=user_pool.user_pool_arn,
            web_acl_arn=waf_web_acl.attr_arn
        )