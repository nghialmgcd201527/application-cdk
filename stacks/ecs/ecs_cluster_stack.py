"""Import Library to  create ECS Cluster."""
from constructs import Construct
from aws_cdk import (
    Stack,
    aws_ecs as ecs,
)

import aws_cdk as core
from helper import config


class ECSCluster(Stack):
    """Class to create ECS Cluster"""

    def __init__(self, scope: Construct, construct_id: str, vpc, **kwargs) -> None:
        super().__init__(scope, construct_id, cross_region_references=True, **kwargs)
        conf = config.Config(self.node.try_get_context("environment"))
        project_name = conf.get("project_name")
        environment = conf.get("environment")

        # create ecs cluster
        self.cluster = ecs.Cluster(
            self,
            "ECSCluster",
            cluster_name=f"{project_name}-{environment}-ecs-cluster",
            vpc=vpc,
            container_insights=True,
        )
        core.CfnOutput(
            self,
            "ECS-Cluster-Name",
            value=self.cluster.cluster_name,
            export_name="ecs-cluster-name",
        )
