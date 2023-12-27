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

        conf = config.Config(self.node.try_get_context("environment"))
        project_name = conf.get("project_name")
        vpc_cidr = conf.get("vpc_cidr")
        tooling_cidr_block = conf.get("tooling_cidr_block")
        tooling_vpc_id = conf.get("tooling_vpc_id")
        tooling_aws_account_id = conf.get("tooling_aws_account_id")
        is_enabled_flow_log = conf.get("is_enabled_flow_log")
        is_created_internet_gateway = conf.get("is_created_internet_gateway")
        vpc_tiers = conf.get("vpc_tiers")
        number_of_nat = conf.get("number_of_nat")
        vpc_endpoints = conf.get("vpc_endpoints")

        # Solution is expected to use 1 or 2 primary AZs for workloads, a 3rd AZ can be defined for out of band services
        # vpc_tiers = {}
        vpc_tiers_objs = {}
        vpc_endpoints_objs = {}
        # vpc_endpoints = {}
        # iam_roles = {}
        # iam_roles_objs = {}

        vpc_tiers = conf.get("vpc_tiers")

        self.vpc = ec2.Vpc(
            self,
            "vpc",
            vpc_name=project_name + "-vpc",
            create_internet_gateway=is_created_internet_gateway,
            ip_addresses=ec2.IpAddresses.cidr(vpc_cidr),
            max_azs=0,
            enable_dns_hostnames=True,
            enable_dns_support=True,
        )
        core.Tags.of(self.vpc).add("Name", project_name + "-" + vpc_cidr + "-vpc")
        core.Tags.of(self.vpc).add(
            "Name",
            project_name + "-vpc-igw",
            include_resource_types=["AWS::EC2::InternetGateway"],
        )

        if is_enabled_flow_log:
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

            flow_log = ec2.FlowLog(
                self,
                "FlowLog",
                resource_type=ec2.FlowLogResourceType.from_vpc(self.vpc),
                destination=ec2.FlowLogDestination.to_cloud_watch_logs(
                    vpc_log_group, vpc_flow_role
                ),
            )
            flow_log.apply_removal_policy(removal_policy)

        for subnet_name, subnet_details in vpc_tiers.items():
            subnet_type, igw, cidr, availability_zone = subnet_details

            vpc_tiers_objs[subnet_name] = ec2.Subnet(
                self,
                f"vpc_tier_{subnet_name}",
                availability_zone=availability_zone,
                cidr_block=cidr,
                vpc_id=self.vpc.vpc_id,  # Replace 'self.vpc.vpc_id' with your VPC ID
            )

            core.Tags.of(vpc_tiers_objs[subnet_name]).add(
                "Name",
                f"{project_name}-{subnet_type}-{availability_zone[-1]}",
            )
        # # create a VPC Peering to Tooling Account
        # self.vpc_peering_tooling = ec2.CfnVPCPeeringConnection(
        #     self,
        #     "VPCPeeringTooling",
        #     peer_vpc_id=tooling_vpc_id,
        #     vpc_id=self.vpc.vpc_id,
        #     peer_owner_id=tooling_aws_account_id,
        #     peer_region=self.region,
        #     peer_role_arn=f"arn:aws:iam::{tooling_vpc_id}:role/accepter_peering_role",
        # )

        def create_nat_gateway_eip(project_name, subnet_name, stack):
            nat_gateway_eip = ec2.CfnEIP(stack, f"eip_{subnet_name}")
            core.Tags.of(nat_gateway_eip).add(
                "Name", f"{project_name}-EIP-{subnet_name}"
            )
            return nat_gateway_eip

        def create_nat_gateway(
            project_name, subnet_name, subnet_id, allocation_id, stack
        ):
            cfn_nat_gateway = ec2.CfnNatGateway(
                stack,
                f"nat_gateway_{subnet_name}",
                subnet_id=subnet_id,
                allocation_id=allocation_id,
            )
            core.Tags.of(cfn_nat_gateway).add(
                "Name", f"{project_name}-NAT-{subnet_name}"
            )
            return cfn_nat_gateway

        def create_route(
            project_name, subnet_name, route_table_id, nat_gateway_id, stack
        ):
            cfn_route = ec2.CfnRoute(
                stack,
                f"route_{subnet_name}",
                route_table_id=route_table_id,
                destination_cidr_block="0.0.0.0/0",
                nat_gateway_id=nat_gateway_id,
            )
            core.Tags.of(cfn_route).add("Name", f"{project_name}-Route-{subnet_name}")

        def create_vpc_peering_route(
            project_name, route_table_id, tooling_cidr_block, vpc_peering_ref, stack
        ):
            cfn_route = ec2.CfnRoute(
                stack,
                f"VPCPeering-Route-{route_table_id}",
                route_table_id=route_table_id,
                destination_cidr_block=tooling_cidr_block,
                gateway_id=vpc_peering_ref,
            )
            core.Tags.of(cfn_route).add(
                "Name", f"{project_name}-VPCPeering-Route-{route_table_id}"
            )

        def create_vpc_endpoint(
            stack, endpoint_name, endpoint_details, vpc, vpc_tiers_objs
        ):
            endpoint_target_sequence = []
            if endpoint_details["vpc_endpoint_type"] == "Gateway":
                for target_name in endpoint_details["subnets"]:
                    endpoint_target_sequence.append(
                        vpc_tiers_objs[target_name].route_table.route_table_id
                    )
            elif endpoint_details["vpc_endpoint_type"] == "Interface":
                for target_name in endpoint_details["subnets"]:
                    endpoint_target_sequence.append(
                        vpc_tiers_objs[target_name].subnet_id
                    )

            endpoint_object = ec2.CfnVPCEndpoint(
                stack,
                f"vpc_endpoint_{endpoint_name}",
                service_name=f"com.amazonaws.{stack.region}.{endpoint_details['service_name']}",
                vpc_id=vpc.vpc_id,
                vpc_endpoint_type=endpoint_details["vpc_endpoint_type"],
                route_table_ids=(
                    endpoint_target_sequence
                    if endpoint_details["vpc_endpoint_type"] == "Gateway"
                    else None
                ),
                subnet_ids=(
                    endpoint_target_sequence
                    if endpoint_details["vpc_endpoint_type"] == "Interface"
                    else None
                ),
                private_dns_enabled=(
                    True
                    if endpoint_details["vpc_endpoint_type"] == "Interface"
                    else False
                ),
            )
            return endpoint_object

        # Create EIP for NAT Gateway
        if number_of_nat == 1:
            nat_gateway_eip = create_nat_gateway_eip(project_name, "public1a", self)
            cfn_nat_gateway = create_nat_gateway(
                project_name,
                "public1a",
                vpc_tiers_objs["public1a"].subnet_id,
                nat_gateway_eip.attr_allocation_id,
                self,
            )
            for subnet_name, subnet_details in vpc_tiers.items():
                subnet_type, igw, cidr, availability_zone = subnet_details
                if subnet_type.startswith("public"):
                    public_subnet = vpc_tiers_objs[subnet_name]
                    public_subnet.add_default_internet_route(
                        self.vpc.internet_gateway_id, self.vpc
                    )

                if subnet_type.startswith("private1"):
                    private_subnet = vpc_tiers_objs[subnet_name]
                    create_route(
                        project_name,
                        subnet_name,
                        private_subnet.route_table.route_table_id,
                        cfn_nat_gateway.ref,
                        self,
                    )
                if subnet_type.startswith("private2"):
                    for endpoint_name, endpoint_details in vpc_endpoints.items():
                        if endpoint_details["service_name"]:
                            if endpoint_name not in vpc_endpoints_objs:
                                endpoint_obj = create_vpc_endpoint(
                                    self,
                                    endpoint_name,
                                    endpoint_details,
                                    self.vpc,
                                    vpc_tiers_objs,
                                )
                                vpc_endpoints_objs[endpoint_name] = endpoint_obj
        elif number_of_nat == 2:
            nat_gateways = {}  # Store NAT gateways per public subnet

            # Create NAT gateways for public subnets
            for subnet_name, subnet_details in vpc_tiers.items():
                subnet_type, igw, cidr, availability_zone = subnet_details

                if subnet_type.startswith("public"):
                    public_subnet = vpc_tiers_objs[subnet_name]
                    public_subnet.add_default_internet_route(
                        self.vpc.internet_gateway_id, self.vpc
                    )
                    nat_gateway_eip = create_nat_gateway_eip(
                        project_name, subnet_name, self
                    )
                    cfn_nat_gateway = create_nat_gateway(
                        project_name,
                        subnet_name,
                        public_subnet.subnet_id,
                        nat_gateway_eip.attr_allocation_id,
                        self,
                    )
                    nat_gateways[
                        availability_zone
                    ] = cfn_nat_gateway  # Store NAT gateway reference

            # Route private subnets to the respective NAT gateways
            for subnet_name, subnet_details in vpc_tiers.items():
                subnet_type, igw, cidr, availability_zone = subnet_details

                if subnet_type.startswith("private1"):
                    private_subnet = vpc_tiers_objs[subnet_name]
                    public_subnet_name = f"public{availability_zone[-1]}"
                    nat_gateway_ref = nat_gateways.get(availability_zone)
                    create_route(
                        project_name,
                        subnet_name,
                        private_subnet.route_table.route_table_id,
                        nat_gateway_ref.attr_nat_gateway_id,
                        self,
                    )

                    # create_vpc_peering_route(
                    #     project_name,
                    #     private_subnet.route_table.route_table_id,
                    #     tooling_cidr_block,
                    #     self.vpc_peering_tooling.ref,
                    #     self,
                    # )
                if subnet_type.startswith("private2"):
                    for endpoint_name, endpoint_details in vpc_endpoints.items():
                        if endpoint_details["service_name"]:
                            if endpoint_name not in vpc_endpoints_objs:
                                endpoint_obj = create_vpc_endpoint(
                                    self,
                                    endpoint_name,
                                    endpoint_details,
                                    self.vpc,
                                    vpc_tiers_objs,
                                )
                                vpc_endpoints_objs[endpoint_name] = endpoint_obj
