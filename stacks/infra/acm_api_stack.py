"""Module import"""
import aws_cdk as core
from constructs import Construct
from aws_cdk import Stack, aws_certificatemanager as acm, aws_route53 as r53
from helper import config


class AcmApiStack(Stack):
    """Class to create ACM"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        conf = config.Config(self.node.try_get_context("environment"))
        web_domain = conf.get("web_domain")
        api_domain = conf.get("api_domain")
        environment = conf.get("environment")
        # Assign my_hosted_zone as the current route53 zone id
        my_hosted_zone = r53.HostedZone.from_lookup(
            self, f"{api_domain}", domain_name=f"{web_domain}"
        )

        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_certificatemanager/Certificate.html
        self.api_domain_cert = acm.Certificate(
            self,
            f"api-domain-cert-{environment}",
            domain_name=f"{api_domain}",
            validation=acm.CertificateValidation.from_dns(my_hosted_zone),
        )
        # export certificate arn to output of cloudformation
        self.api_domain_cert_arn = self.api_domain_cert.certificate_arn
        core.CfnOutput(
            self,
            "api_cert_arn",
            value=self.api_domain_cert_arn,
            export_name="api-cert-arn",
        )
