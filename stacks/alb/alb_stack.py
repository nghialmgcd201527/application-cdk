from constructs import Construct
from aws_cdk import (
    Stack,
    aws_elasticloadbalancingv2 as alb,
    aws_ec2 as ec2,
    aws_cloudfront as cloudfront,
    aws_route53 as r53,
)
from aws_cdk.aws_certificatemanager import Certificate
import aws_cdk as core
from helper import config


class AlbStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        tls_certificate: Certificate,
        waf_web_acl_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, cross_region_references=True, **kwargs)
        conf = config.Config(self.node.try_get_context("environment"))
        project_name = conf.get("project_name")
        environment = conf.get("environment")
        acm_arn = core.Fn.import_value("api-cert-arn")
        web_arn = tls_certificate.certificate_arn
        api_domain = conf.get("api_domain")
        web_domain = conf.get("web_domain")

        public_subnet_ids = []
        public_subnet_ids.append(core.Fn.import_value("PublicSubnet-1"))
        public_subnet_ids.append(core.Fn.import_value("PublicSubnet-2"))

        my_hosted_zone = r53.HostedZone.from_lookup(
            self, f"{api_domain}", domain_name=f"{web_domain}"
        )
        web_acl_id = core.Fn.import_value("api-acl-arn")

        # create alb security group
        self.alb_sec_group = ec2.SecurityGroup(
            self,
            f"{project_name}-ALB-sg",
            description="ALB Public Facing Security Group",
            vpc=vpc,
            allow_all_outbound=True,
        )
        self.alb_sec_group.add_ingress_rule(
            ec2.Peer.ipv4("0.0.0.0/0"), ec2.Port.tcp(443), "HTTPS Access"
        )
        self.alb_sec_group.add_ingress_rule(
            ec2.Peer.ipv4("0.0.0.0/0"), ec2.Port.tcp(80), "HTTP Access"
        )

        self.private_security_group = ec2.SecurityGroup(
            self,
            f"{project_name}-Private-SG",
            vpc=vpc,
            description="Private Security Group - ECS Container",
            allow_all_outbound=True,
        )

        # add ingress rule for private_security_group all tcp from alb_sec_group
        self.private_security_group.connections.allow_from(
            self.alb_sec_group, ec2.Port.all_traffic(), "Ingress from ALB"
        )
        # add ingress rule for private_security_group range tcp from 5000 to 5010 from private_security_group

        self.private_security_group.connections.allow_from(
            self.private_security_group,
            ec2.Port.tcp_range(5000, 5010),
            "Ingress from ECS",
        )

        # create application loadbalancer
        self.alb = alb.CfnLoadBalancer(
            self,
            f"{project_name}-alb-{environment}",
            name=f"{project_name}-alb-{environment}",
            scheme="internet-facing",
            type="application",
            subnets=public_subnet_ids,
            security_groups=[self.alb_sec_group.security_group_id],
            load_balancer_attributes=[
                alb.CfnLoadBalancer.LoadBalancerAttributeProperty(
                    key="deletion_protection.enabled", value="false"
                ),
                alb.CfnLoadBalancer.LoadBalancerAttributeProperty(
                    key="routing.http2.enabled", value="true"
                ),
                #    aws_elasticloadbalancingv2.CfnLoadBalancer.LoadBalancerAttributeProperty(
                #        key="access_logs.s3.bucket",
                #        value="true"),
            ],
        )

        # create listeners for alb
        self.http_listener = alb.CfnListener(
            self,
            "http-listener",
            default_actions=[
                alb.CfnListener.ActionProperty(
                    type="redirect",
                    redirect_config=alb.CfnListener.RedirectConfigProperty(
                        status_code="HTTP_301",
                        port="443",
                        protocol="HTTPS",
                        host="#{host}",
                        path="/#{path}",
                        query="#{query}",
                    ),
                )
            ],
            load_balancer_arn=self.alb.ref,
            port=80,
            protocol="HTTP",
        )
        self.https_listener = alb.CfnListener(
            self,
            "https-listener",
            default_actions=[
                alb.CfnListener.ActionProperty(
                    type="fixed-response",
                    fixed_response_config=alb.CfnListener.FixedResponseConfigProperty(
                        message_body="Fixed response content",
                        status_code="503",
                        content_type="text/plain",
                    ),
                )
            ],
            load_balancer_arn=self.alb.ref,
            port=443,
            protocol="HTTPS",
            ssl_policy="ELBSecurityPolicy-TLS-1-2-Ext-2018-06",
            certificates=[alb.CfnListener.CertificateProperty(certificate_arn=acm_arn)],
        )

        # CLOUDFRONT OAI FOR ALB
        alb_cloudfront_identity = cloudfront.CfnCloudFrontOriginAccessIdentity(
            self,
            "CloudFrontCloudFrontOriginAccessIdentity",
            cloud_front_origin_access_identity_config={"comment": "ALB-CF-OAI"},
        )
        # CLOUDFRONT DISTRIBUTION
        alb_cloudfrontdistribution = cloudfront.CfnDistribution(
            self,
            "ALBCloudFrontDistribution",
            distribution_config=(
                cloudfront.CfnDistribution.DistributionConfigProperty(
                    aliases=[api_domain],
                    origins=[
                        cloudfront.CfnDistribution.OriginProperty(
                            domain_name=self.alb.attr_dns_name,
                            id=self.alb.attr_dns_name,
                            origin_path="",
                            connection_attempts=3,
                            connection_timeout=10,
                            custom_origin_config=cloudfront.CfnDistribution.CustomOriginConfigProperty(
                                http_port=80,
                                https_port=443,
                                origin_protocol_policy="https-only",
                                origin_ssl_protocols=["TLSv1.2"],
                                origin_read_timeout=30,
                            ),
                        )
                    ],
                    default_cache_behavior=cloudfront.CfnDistribution.DefaultCacheBehaviorProperty(
                        allowed_methods=[
                            "HEAD",
                            "DELETE",
                            "POST",
                            "GET",
                            "OPTIONS",
                            "PUT",
                            "PATCH",
                        ],
                        cached_methods=["HEAD", "GET", "OPTIONS"],
                        compress=False,
                        default_ttl=0,
                        target_origin_id=self.alb.attr_dns_name,
                        viewer_protocol_policy="redirect-to-https",
                        forwarded_values=cloudfront.CfnDistribution.ForwardedValuesProperty(
                            cookies=cloudfront.CfnDistribution.CookiesProperty(
                                forward="none"
                            ),
                            headers=[
                                "Authorization",
                                "CloudFront-Viewer-Time-Zone",
                                "CloudFront-Viewer-Country-Region-Name",
                                "CloudFront-Viewer-Country-Name",
                                "CloudFront-Viewer-Longitude",
                                "User-Agent",
                                "CloudFront-Viewer-City",
                                "CloudFront-Viewer-Latitude",
                                "Host",
                            ],
                            query_string=True,
                        ),
                    ),
                    price_class="PriceClass_100",
                    enabled=True,
                    viewer_certificate=cloudfront.CfnDistribution.ViewerCertificateProperty(
                        acm_certificate_arn=web_arn,  # update here
                        minimum_protocol_version="TLSv1.2_2021",
                        ssl_support_method="sni-only",
                    ),
                    restrictions=cloudfront.CfnDistribution.RestrictionsProperty(
                        geo_restriction=cloudfront.CfnDistribution.GeoRestrictionProperty(
                            restriction_type="none"
                        )
                    ),
                    # web_acl_id=web_acl_id,
                    # http_version="http2",
                    # default_root_object="",
                    # ipv6_enabled=False,
                    cache_behaviors=[
                        # cloudfront.CfnDistribution.CacheBehaviorProperty(
                        #     allowed_methods=[
                        #         "HEAD", "DELETE", "POST", "GET", "OPTIONS", "PUT", "PATCH"],
                        #     compress=False,
                        #     cache_policy_id="4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
                        #     path_pattern="/locale-svc/*",
                        #     smooth_streaming=False,
                        #     target_origin_id="origin_locale_svc",
                        #     viewer_protocol_policy="redirect-to-https"
                        # ),
                        # cloudfront.CfnDistribution.CacheBehaviorProperty(
                        #     allowed_methods=[
                        #         "HEAD", "DELETE", "POST", "GET", "OPTIONS", "PUT", "PATCH"],
                        #     compress=False,
                        #     cache_policy_id="4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
                        #     path_pattern="/appointment-svc/*",
                        #     smooth_streaming=False,
                        #     target_origin_id="origin_appointment_svc",
                        #     viewer_protocol_policy="redirect-to-https"
                        # ),
                        # cloudfront.CfnDistribution.CacheBehaviorProperty(
                        #     allowed_methods=[
                        #         "HEAD", "DELETE", "POST", "GET", "OPTIONS", "PUT", "PATCH"],
                        #     compress=False,
                        #     ess=False,
                        #     cache_policy_id="4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
                        #     path_pattern="/notification-svc/*",
                        #     smooth_streaming=False,
                        #     cache_policy_id="4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
                        #     target_origin_id="origin_notification_svc",
                        #     viewer_protocol_policy="redirect-to-https"
                        # )
                    ],
                )
            ),
        )

        api_record = r53.CfnRecordSetGroup(
            self,
            "ALB-A-Record",
            record_sets=[
                r53.CfnRecordSetGroup.RecordSetProperty(
                    name=api_domain,
                    type="A",
                    alias_target=r53.CfnRecordSetGroup.AliasTargetProperty(
                        hosted_zone_id="Z2FDTNDATAQYW2",  # for china region Z3RFFRIM2A3IF5
                        dns_name=alb_cloudfrontdistribution.attr_domain_name,
                    ),
                )
            ],
            hosted_zone_id=my_hosted_zone.hosted_zone_id,
        )
        core.CfnOutput(self, "ALB-ARN", value=self.alb.ref, export_name="alb-arn")
        core.CfnOutput(
            self,
            "HTTP-Listener-ARN",
            value=self.http_listener.ref,
            export_name="http-listener",
        )
        core.CfnOutput(
            self,
            "HTTPS-Listener-ARN",
            value=self.https_listener.ref,
            export_name="https-listener",
        )
