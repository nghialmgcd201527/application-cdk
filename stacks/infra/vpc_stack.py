"""Import Module."""
import aws_cdk as core
from constructs import Construct
from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_ec2 as ec2,
    RemovalPolicy,
    aws_logs as logs,
)
from helper import config


class VPCStack(Stack):
    """Class to create VPC"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        removal_policy: RemovalPolicy = RemovalPolicy.RETAIN,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc_flow_role = iam.Role(
            self,
            "Flow-Log-Role",
            assumed_by=iam.ServicePrincipal("vpc-flow-logs.amazonaws.com"),
        )

        vpc_log_group = logs.LogGroup(
            self,
            "VPC-Log-Group",
            removal_policy=removal_policy,
            retention=logs.RetentionDays.ONE_YEAR,
        )
        conf = config.Config(self.node.try_get_context("environment"))
        project_name = conf.get("project_name")
        vpc_cidr = conf.get("vpc_cidr")
        tooling_cidr_block = conf.get("tooling_cidr_block")
        vpc_name = f"{project_name}-VPC-{vpc_cidr}"
        general_subnet = conf.get("general_subnet")
        non_general_subnet = conf.get("non_general_subnet")
        tooling_vpc_id = conf.get("tooling_vpc_id")
        tooling_aws_account_id = conf.get("tooling_aws_account_id")

        self.vpc = ec2.Vpc(
            self,
            vpc_name,
            ip_addresses=ec2.IpAddresses.cidr(vpc_cidr),
            max_azs=2,
            enable_dns_hostnames=True,
            enable_dns_support=True,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=general_subnet,
                ),
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    map_public_ip_on_launch=True,
                    cidr_mask=general_subnet,
                ),
                ec2.SubnetConfiguration(
                    name="Isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=non_general_subnet,
                ),
                ec2.SubnetConfiguration(
                    name="TGW",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=non_general_subnet,
                ),
            ],
        )
        core.Tags.of(self.vpc).add("Name", f"{project_name}-VPC-{vpc_cidr}")

        flow_log = ec2.FlowLog(
            self,
            "FlowLog",
            resource_type=ec2.FlowLogResourceType.from_vpc(self.vpc),
            destination=ec2.FlowLogDestination.to_cloud_watch_logs(
                vpc_log_group, vpc_flow_role
            ),
        )
        flow_log.apply_removal_policy(removal_policy)
        # Filter out subnets
        private_subnets_isolated = self.vpc.select_subnets(subnet_group_name="Isolated")
        private_subnets_private = self.vpc.select_subnets(subnet_group_name="Private")
        private_subnets_tgw = self.vpc.select_subnets(subnet_group_name="TGW")
        public_subnets = self.vpc.select_subnets(subnet_type=ec2.SubnetType.PUBLIC)

        index = 1
        # Naming Subnet
        for subnet in private_subnets_tgw.subnets:
            core.Tags.of(subnet).add("Name", f"{project_name}-TGW-" + str(index))
            core.CfnOutput(
                self,
                f"TGW-Subnet-{index}",
                value=private_subnets_tgw.subnet_ids[index - 1],
                export_name=f"TGWSubnet-{index}",
            )
            index = index + 1
        index = 1
        for subnet in private_subnets_isolated.subnets:
            core.Tags.of(subnet).add("Name", f"{project_name}-Isolated-" + str(index))
            core.CfnOutput(
                self,
                f"Isolated-Subnet-{index}",
                value=private_subnets_isolated.subnet_ids[index - 1],
                export_name=f"IsolatedSubnet-{index}",
            )
            index = index + 1
        index = 1
        for subnet in private_subnets_private.subnets:
            core.Tags.of(subnet).add("Name", f"{project_name}-Private-" + str(index))
            core.CfnOutput(
                self,
                f"Private-Subnet-{index}",
                value=private_subnets_private.subnet_ids[index - 1],
                export_name=f"PrivateSubnet-{index}",
            )
            index = index + 1
        index = 1
        for subnet in public_subnets.subnets:
            core.Tags.of(subnet).add("Name", f"{project_name}-public-" + str(index))
            core.CfnOutput(
                self,
                f"Public-Subnet-{index}",
                value=public_subnets.subnet_ids[index - 1],
                export_name=f"PublicSubnet-{index}",
            )
            index = index + 1

        core.CfnOutput(self, "VpcID", value=self.vpc.vpc_id, export_name="VpcID")
        core.CfnOutput(
            self,
            "Private-Subnets",
            value=",".join(
                str(subnets) for subnets in private_subnets_private.subnet_ids
            ),
        )
        core.CfnOutput(
            self,
            "Isolated-Subnets",
            value=",".join(
                str(subnets) for subnets in private_subnets_isolated.subnet_ids
            ),
        )
        core.CfnOutput(
            self,
            "TGW-Subnets",
            value=",".join(str(subnets) for subnets in private_subnets_tgw.subnet_ids),
        )

        # create a VPC Peering to Tooling Account
        self.vpc_peering_tooling = ec2.CfnVPCPeeringConnection(
            self,
            "VPCPeeringTooling",
            peer_vpc_id=tooling_vpc_id,
            vpc_id=self.vpc.vpc_id,
            peer_owner_id=tooling_aws_account_id,
            peer_region=self.region,
            peer_role_arn=f"arn:aws:iam::{tooling_vpc_id}:role/accepter_peering_role",
        )

        # get private Route table ids from vpc, but only the subnet with tag isolation
        private_route_table_ids = [
            rt.route_table_id
            for rt in self.vpc.private_subnets
            if "Private" in str(rt.node.default_child)
        ]

        # add route for each route table ids
        for route_table_id in private_route_table_ids:
            ec2.CfnRoute(
                self,
                f"Route-Table-{route_table_id}",
                route_table_id=route_table_id,
                destination_cidr_block=tooling_cidr_block,
                gateway_id=self.vpc_peering_tooling.ref,
            )

        # create a VPC endpoint and endpoint interface with located at Isolated subnet
        # self.vpc.add_gateway_endpoint(
        #     "S3Endpoint",
        #     service=ec2.GatewayVpcEndpointAwsService.S3,
        #     subnets=[private_subnets_isolated]
        # )
