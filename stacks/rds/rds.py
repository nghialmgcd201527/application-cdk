"""Import Module."""
import aws_cdk as core
from aws_cdk import aws_iam as iam, aws_ec2 as ec2, aws_rds as rds, Stack
from constructs import Construct
from helper import config


class RDSStack(Stack):
    """Class to create RDS"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc,
        jump_sec_group: ec2.SecurityGroup,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        conf = config.Config(self.node.try_get_context("environment"))
        private_subnets_ids = []
        private_subnets_ids.append(core.Fn.import_value("PrivateSubnet-1"))
        private_subnets_ids.append(core.Fn.import_value("PrivateSubnet-2"))

        tooling_cidr_block = conf.get("tooling_cidr_block")
        api_service = conf.get("api_service_name")
        account_service = conf.get("account_service_name")
        instance_type = conf.get("instance_type")
        rds_certification = conf.get("rds_certification")
        is_enabled_multiaz = conf.get("is_enabled_multiaz")
        # Create database security group for rds
        self.database_sec_group = ec2.SecurityGroup(
            self, "rds-sg", vpc=vpc, allow_all_outbound=False
        )
        # Add ingress rule for database security group
        self.database_sec_group.add_ingress_rule(
            jump_sec_group, ec2.Port.tcp(5432), "Allow isolated sg RDS Access "
        )
        # self.database_sec_group.add_ingress_rule(
        #     self.isolated_sec_group, ec2.Port.tcp(5432), "Allow jumbox sg RDS Access")
        self.database_sec_group.add_ingress_rule(
            ec2.Peer.ipv4(tooling_cidr_block),
            ec2.Port.tcp(5432),
            "Allow tooling subnet RDS Access ",
        )
        # Create RDS subnet group
        rds_subnet_group = rds.CfnDBSubnetGroup(
            self,
            "api-rds-subnet-group",
            db_subnet_group_description="RDS Subnet Group",
            subnet_ids=private_subnets_ids,
            db_subnet_group_name="api-rds-subnet-group",
        )
        # Create RDS monitoring role
        monitoring_role_arn = iam.Role(
            self,
            "MyRDSMonitoringRole",
            assumed_by=iam.ServicePrincipal("monitoring.rds.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonRDSEnhancedMonitoringRole"
                )
            ],
        )

        # create RDS parameter group
        postgres_parameter_group = rds.CfnDBParameterGroup(
            self,
            "postgres-parameter-group",
            family="postgres15",
            description="postgres15 parameter group",
        )

        db_instance_identifiers = [account_service, api_service]
        for identifier in db_instance_identifiers:
            rds.CfnDBInstance(
                self,
                f"{identifier}-rds-instance",
                engine="postgres",
                engine_version="15",
                ca_certificate_identifier=rds_certification,
                multi_az=is_enabled_multiaz,
                auto_minor_version_upgrade=True,
                db_subnet_group_name=rds_subnet_group.db_subnet_group_name,
                db_instance_identifier=f"{identifier}-rds-instance",
                db_parameter_group_name=postgres_parameter_group.ref,
                db_instance_class=instance_type,
                vpc_security_groups=[self.database_sec_group.security_group_id],
                allocated_storage="20",
                db_name=f"{identifier.replace('-','_')}_db",
                publicly_accessible=False,
                storage_encrypted=True,
                deletion_protection=True,
                preferred_maintenance_window="Mon:12:58-Mon:13:28",
                preferred_backup_window="07:16-07:46",
                enable_performance_insights=True,
                performance_insights_retention_period=7,
                monitoring_interval=30,
                monitoring_role_arn=monitoring_role_arn.role_arn,
                manage_master_user_password=True,
                master_username="superadmin",
            )
