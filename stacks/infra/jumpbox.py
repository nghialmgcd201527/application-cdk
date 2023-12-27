"""Module Import."""
import aws_cdk as core
from constructs import Construct
from helper import config
from aws_cdk.aws_iam import Role, ManagedPolicy, ServicePrincipal, CfnInstanceProfile
from aws_cdk import Stack, aws_ec2 as ec2


class JumboxStack(Stack):
    """Class to create a jumpbox"""

    def __init__(self, scope: Construct, construct_id: str, vpc, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Declare vars
        conf = config.Config(self.node.try_get_context("environment"))
        stage = conf.get("stage")
        region = conf.get("region")
        # import value
        # vpc = core.Fn.import_value("VpcID")
        public_subnet = core.Fn.import_value("PublicSubnet-1")
        role = Role(
            self,
            "SSM-role-access",
            role_name="SSM-Role",
            assumed_by=ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ],
        )

        # AMI image ID table
        # AMI_ID_table = CfnMapping(self, "AMI_ID_table",
        #     mapping={
        #         "us-west-2": {
        #             "AMI": "ami-03f65b8614a860c29"
        #         },
        #         "ap-southeast-1": {
        #             "AMI": "ami-0df7a207adb9748c7"
        #         },
        #         "ap-southeast-2": {
        #             "AMI": "ami-0310483fb2b488153"
        #         }
        #     }
        # )
        # Security group
        self.jump_sec_group = ec2.SecurityGroup(
            self,
            "Jump-sg",
            vpc=vpc,
            allow_all_outbound=True,
            description="Jumpbox security group",
        )
        # Basion host
        self.instance_profile = CfnInstanceProfile(
            self, "Jumpbox-Instance-Profile", roles=[role.role_name]
        )

        self.bastion_host = ec2.CfnInstance(
            self,
            "BastionHost",
            # image_id=AMI_ID_table.find_in_map(region, "AMI"),
            image_id="ami-03f65b8614a860c29",
            instance_type="t3a.nano",
            availability_zone=f"{region}a",
            # block_device_mappings=[
            #     ec2.CfnInstance.BlockDeviceMappingProperty(
            #         device_name="deviceName",
            #         # the properties below are optional
            #         ebs=ec2.CfnInstance.EbsProperty(
            #             delete_on_termination=False, encrypted=True
            #         ),
            #         no_device=ec2.CfnInstance.NoDeviceProperty(),
            #         virtual_name="virtualName",
            #     )
            # ],
            tenancy="default",
            ebs_optimized=False,
            security_group_ids=[self.jump_sec_group.security_group_id],
            iam_instance_profile=self.instance_profile.ref,
            subnet_id=public_subnet,
            tags=[{"key": "Name", "value": f"Jumpbox-{stage}"}],
        )

        # ec2.CfnFlowLog(
        #     self, 'FlowLogs',y
        #     resource_id=self.vpc.vpc_id,
        #     resource_type='VPC',
        #     traffic_type='ALL',
        #     deliver_logs_permission_arn=vpc_flow_role.role_arn,
        #     log_destination_type='cloud-watch-logs',
        #     log_group_name=vpc_log_group.log_group_name)
