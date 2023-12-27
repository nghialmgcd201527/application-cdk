"""Module Import Library"""
import aws_cdk as core

from aws_cdk import (
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as albv2,
    aws_ecr as ecr,
    aws_codedeploy as codedeploy,
    aws_s3 as s3,
    aws_codepipeline as codepipeline,
    Duration,
    Stack,
    RemovalPolicy,
)

from constructs import Construct
from helper import config


class ApiSvcStack(Stack):
    """Class to create API Service"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc,
        https_listener_arn,
        cluster,
        private_sg,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # declare vars
        conf = config.Config(self.node.try_get_context("environment"))
        project_name = conf.get("project_name")
        environment = conf.get("environment")
        service_name = conf.get("api_service_name")
        service_shortname = conf.get("api_service_shortname")
        container_name = service_name
        container_port = 5000
        priority = conf.get("api_service_priority")
        desired_count = 1

        private_subnets_ids = []
        private_subnets_ids.append(core.Fn.import_value("PrivateSubnet-1"))
        private_subnets_ids.append(core.Fn.import_value("PrivateSubnet-2"))
        # role import
        task_role_arn = core.Fn.import_value("task-role-arn")
        task_execution_role_arn = core.Fn.import_value("task-execution-role-arn")
        codedeploy_role_arn = core.Fn.import_value("codedeploy-role-arn")
        codepipeline_role_arn = core.Fn.import_value("codepipeline-role-arn")

        # ECR
        self.repository = ecr.CfnRepository(
            self,
            "be_repository",
            image_scanning_configuration=ecr.CfnRepository.ImageScanningConfigurationProperty(
                scan_on_push=True
            ),
            image_tag_mutability="MUTABLE",
            # lifecycle_policy=ecr.LifecycleRule(
            #     description="store only 7 latest iamges",
            #     rule_priority=1,
            #     tag_status=ecr.TagStatus.UNTAGGED,
            #     max_image_count=7
            # ),
            repository_name=service_name,
            # tags=[{"Name": "{service_name}"}, {
            #     "Environment": "{environment}"}]
        )

        self.task_def = ecs.CfnTaskDefinition(
            self,
            f"{service_name}-task_definition",
            container_definitions=[
                ecs.CfnTaskDefinition.ContainerDefinitionProperty(
                    image="datahouseasia/base_image:latest",
                    name=container_name,
                    port_mappings=[
                        ecs.CfnTaskDefinition.PortMappingProperty(
                            protocol="tcp",
                            host_port=container_port,
                            container_port=container_port,
                        )
                    ],
                    environment=[
                        ecs.CfnTaskDefinition.KeyValuePairProperty(
                            name="APP_NAME", value=service_shortname
                        ),
                        ecs.CfnTaskDefinition.KeyValuePairProperty(
                            name="APP_PORT", value=f"{container_port}"
                        ),
                    ],
                    log_configuration=ecs.CfnTaskDefinition.LogConfigurationProperty(
                        log_driver="awslogs",
                        options={
                            "awslogs-group": f"{service_name}",
                            "awslogs-region": self.region,
                            "awslogs-stream-prefix": f"{project_name}",
                            "awslogs-create-group": "true",
                        },
                    ),
                )
            ],
            cpu="256",
            memory="1024",
            execution_role_arn=task_role_arn,
            task_role_arn=task_execution_role_arn,
            network_mode="awsvpc",
            family=service_name,
            requires_compatibilities=["FARGATE"],
            runtime_platform=ecs.CfnTaskDefinition.RuntimePlatformProperty(
                cpu_architecture="X86_64", operating_system_family="LINUX"
            ),
        )

        # create blue target group and green target group
        blue_target_group = albv2.ApplicationTargetGroup(
            self,
            f"{service_name}-blue-tg",
            port=container_port,
            protocol=albv2.ApplicationProtocol.HTTP,
            target_group_name=f"{service_name}-blue-tg",
            target_type=albv2.TargetType.IP,
            health_check=albv2.HealthCheck(
                enabled=True,
                path=f"/{service_shortname}/health",
                protocol=albv2.Protocol.HTTP,
                port=f"{container_port}",
                healthy_threshold_count=2,
                timeout=Duration.seconds(5),
                unhealthy_threshold_count=2,
                interval=Duration.seconds(30),
            ),
            vpc=vpc,
        )

        green_target_group = albv2.ApplicationTargetGroup(
            self,
            f"{service_name}-green-tg",
            port=container_port,
            protocol=albv2.ApplicationProtocol.HTTP,
            target_group_name=f"{service_name}-green-tg",
            target_type=albv2.TargetType.IP,
            health_check=albv2.HealthCheck(
                enabled=True,
                path=f"/{service_shortname}/health",
                protocol=albv2.Protocol.HTTP,
                port=f"{container_port}",
                healthy_threshold_count=2,
                timeout=Duration.seconds(5),
                unhealthy_threshold_count=2,
                interval=Duration.seconds(30),
            ),
            vpc=vpc,
        )

        service_listener_rule = albv2.CfnListenerRule(
            self,
            f"{service_name}-listener-rule",
            listener_arn=https_listener_arn,
            priority=priority,
            actions=[
                albv2.CfnListenerRule.ActionProperty(
                    type="forward", target_group_arn=blue_target_group.target_group_arn
                )
            ],
            conditions=[
                albv2.CfnListenerRule.RuleConditionProperty(
                    field="path-pattern",
                    path_pattern_config=albv2.CfnListenerRule.PathPatternConfigProperty(
                        values=[
                            f"/{service_shortname}",
                            f"/{service_shortname}/",
                            f"/{service_shortname}/*",
                        ]
                    ),
                )
            ],
        )

        self.ecs_service = ecs.CfnService(
            self,
            f"{service_name}",
            cluster=cluster.cluster_name,
            service_name=service_name,
            load_balancers=[
                ecs.CfnService.LoadBalancerProperty(
                    container_name=container_name,
                    target_group_arn=blue_target_group.target_group_arn,
                    container_port=container_port,
                )
            ],
            desired_count=desired_count,
            launch_type="FARGATE",
            task_definition=self.task_def.ref,
            deployment_configuration=ecs.CfnService.DeploymentConfigurationProperty(
                maximum_percent=200, minimum_healthy_percent=100
            ),
            network_configuration=ecs.CfnService.NetworkConfigurationProperty(
                awsvpc_configuration=ecs.CfnService.AwsVpcConfigurationProperty(
                    assign_public_ip="DISABLED",
                    security_groups=[private_sg],
                    subnets=private_subnets_ids,
                )
            ),
            health_check_grace_period_seconds=0,
            deployment_controller=ecs.CfnService.DeploymentControllerProperty(
                type="CODE_DEPLOY"
            ),
        )

        # create CodeDeploy application
        self.service_codedeploy_app = codedeploy.CfnApplication(
            self,
            f"{service_name}-codedeploy-app",
            application_name=f"{service_name}-codedeploy-app",
            compute_platform="ECS",
        )

        # Create CodeDeploy Deployment Group
        self.service_codedeploy_deployment_group = codedeploy.CfnDeploymentGroup(
            self,
            f"{service_name}-codedeploy-deployment-group",
            deployment_group_name=f"{service_name}-codedeploy-deployment-group",
            application_name=self.service_codedeploy_app.application_name,
            service_role_arn=codedeploy_role_arn,
            blue_green_deployment_configuration=codedeploy.CfnDeploymentGroup.BlueGreenDeploymentConfigurationProperty(
                deployment_ready_option=codedeploy.CfnDeploymentGroup.DeploymentReadyOptionProperty(
                    action_on_timeout="CONTINUE_DEPLOYMENT"
                ),
                terminate_blue_instances_on_deployment_success=codedeploy.CfnDeploymentGroup.BlueInstanceTerminationOptionProperty(
                    action="TERMINATE", termination_wait_time_in_minutes=5
                ),
            ),
            deployment_config_name="CodeDeployDefault.ECSAllAtOnce",
            alarm_configuration=codedeploy.CfnDeploymentGroup.AlarmConfigurationProperty(
                enabled=False, ignore_poll_alarm_failure=False
            ),
            auto_rollback_configuration=codedeploy.CfnDeploymentGroup.AutoRollbackConfigurationProperty(
                enabled=True, events=["DEPLOYMENT_FAILURE"]
            ),
            deployment_style=codedeploy.CfnDeploymentGroup.DeploymentStyleProperty(
                deployment_type="BLUE_GREEN", deployment_option="WITH_TRAFFIC_CONTROL"
            ),
            ecs_services=[
                codedeploy.CfnDeploymentGroup.ECSServiceProperty(
                    cluster_name=cluster.cluster_name,
                    service_name=self.ecs_service.attr_name,
                )
            ],
            load_balancer_info=codedeploy.CfnDeploymentGroup.LoadBalancerInfoProperty(
                target_group_pair_info_list=[
                    codedeploy.CfnDeploymentGroup.TargetGroupPairInfoProperty(
                        prod_traffic_route=codedeploy.CfnDeploymentGroup.TrafficRouteProperty(
                            listener_arns=[https_listener_arn]
                        ),
                        target_groups=[
                            codedeploy.CfnDeploymentGroup.TargetGroupInfoProperty(
                                name=f"{service_name}-blue-tg"
                            ),
                            codedeploy.CfnDeploymentGroup.TargetGroupInfoProperty(
                                name=f"{service_name}-green-tg"
                            ),
                        ],
                    )
                ]
            ),
        )
        ecs_artifact_bucket = s3.Bucket(
            self,
            f"{service_name}-ecs-artifact-bucket",
            bucket_name=f"{project_name}-{service_name}-{environment}-artifact-ecs".lower(),
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )
        codepipeline_artifact_bucket = s3.Bucket(
            self,
            f"{service_name}-{environment}-pipeline-arti",
            bucket_name=f"{service_name}-{environment}-pipeline-arti",
            removal_policy=RemovalPolicy.DESTROY,
            versioned=False,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        service_code_pipeline = codepipeline.CfnPipeline(
            self,
            f"{service_name}-codepipeline-{environment}",
            role_arn=codepipeline_role_arn,
            artifact_store=codepipeline.CfnPipeline.ArtifactStoreProperty(
                location=codepipeline_artifact_bucket.bucket_name, type="S3"
            ),
            stages=[
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    name="S3Source",
                    actions=[
                        codepipeline.CfnPipeline.ActionDeclarationProperty(
                            name="Source",
                            action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                                category="Source",
                                owner="AWS",
                                version="1",
                                provider="S3",
                            ),
                            configuration={
                                "PollForSourceChanges": "false",
                                "S3Bucket": ecs_artifact_bucket.bucket_name,
                                "S3ObjectKey": "appspec.zip",
                            },
                            output_artifacts=[
                                codepipeline.CfnPipeline.OutputArtifactProperty(
                                    name="appspecartifact"
                                )
                            ],
                            run_order=1,
                        )
                    ],
                ),
                codepipeline.CfnPipeline.StageDeclarationProperty(
                    name="DeployBlueGreen",
                    actions=[
                        codepipeline.CfnPipeline.ActionDeclarationProperty(
                            name="Deploy",
                            action_type_id=codepipeline.CfnPipeline.ActionTypeIdProperty(
                                category="Deploy",
                                owner="AWS",
                                provider="CodeDeployToECS",
                                version="1",
                            ),
                            configuration={
                                "AppSpecTemplateArtifact": "appspecartifact",
                                "AppSpecTemplatePath": "appspec.yml",
                                "ApplicationName": self.service_codedeploy_app.application_name,
                                "DeploymentGroupName": self.service_codedeploy_deployment_group.deployment_group_name,
                                "Image1ArtifactName": "appspecartifact",
                                "Image1ContainerName": "IMAGE1_NAME",
                                "TaskDefinitionTemplateArtifact": "appspecartifact",
                                "TaskDefinitionTemplatePath": "taskdef.json",
                            },
                            input_artifacts=[
                                codepipeline.CfnPipeline.InputArtifactProperty(
                                    name="appspecartifact"
                                )
                            ],
                            run_order=1,
                        )
                    ],
                ),
            ],
        )
        scale_target = scaling.ScalableTarget(
            self,
            f"ecs-{service_name}-{environment}-scale-target",
            service_namespace=scaling.ServiceNamespace.ECS,
            max_capacity=max_capacity,
            min_capacity=min_capacity,
            resource_id=f"service/{cluster.cluster_name}/{self.ecs_service.attr_name}",
            scalable_dimension="ecs:service:DesiredCount",
        )

        cpu_high_metric_policy = scaling.CfnScalingPolicy(
            self,
            f"ecs-{service_name}-{environment}-scale-up-policy",
            policy_name=f"ecs-{service_name}-{environment}-scale-up-policy",
            policy_type="StepScaling",
            resource_id=scale_target.scalable_target_id,
            scalable_dimension="ecs:service:DesiredCount",
            step_scaling_policy_configuration=scaling.CfnScalingPolicy.StepScalingPolicyConfigurationProperty(
                adjustment_type="ChangeInCapacity",
                cooldown=60,
                metric_aggregation_type="Maximum",
                step_adjustments=[
                    scaling.CfnScalingPolicy.StepAdjustmentProperty(
                        metric_interval_lower_bound=0, scaling_adjustment=1
                    )
                ],
            ),
        )

        cpu_low_metric_policy = scaling.CfnScalingPolicy(
            self,
            f"ecs-{service_name}-{environment}-scale-down-policy",
            policy_name=f"ecs-{service_name}-{environment}-scale-down-policy",
            policy_type="StepScaling",
            resource_id=scale_target.scalable_target_id,
            scalable_dimension="ecs:service:DesiredCount",
            step_scaling_policy_configuration=scaling.CfnScalingPolicy.StepScalingPolicyConfigurationProperty(
                adjustment_type="ChangeInCapacity",
                cooldown=60,
                metric_aggregation_type="Maximum",
                step_adjustments=[
                    scaling.CfnScalingPolicy.StepAdjustmentProperty(
                        metric_interval_lower_bound=0, scaling_adjustment=-1
                    )
                ],
            ),
        )

        cpu_high_metric = cloudwatch.CfnAlarm(
            self,
            f"ecs-{service_name}-{environment}-cpu-high",
            alarm_name=f"ecs-{service_name}-{environment}-cpu-high",
            comparison_operator="GreaterThanOrEqualToThreshold",
            metric_name="CPUUtilization",
            namespace="AWS/ECS",
            period=120,
            statistic="Maximum",
            threshold=ecs_high_cpu_threshold,
            alarm_description="ECS CPU above threshold",
            dimensions=[
                cloudwatch.CfnAlarm.DimensionProperty(
                    name="ClusterName", value=cluster.cluster_name
                ),
                cloudwatch.CfnAlarm.DimensionProperty(
                    name="ServiceName",
                    value=self.ecs_service.attr_name,
                ),
            ],
            alarm_actions=[cpu_high_metric_policy.attr_id],
            evaluation_periods=1,
        )

        cpu_low_metric = cloudwatch.CfnAlarm(
            self,
            f"ecs-{service_name}-{environment}-cpu-low",
            alarm_name=f"ecs-{service_name}-{environment}-cpu-low",
            comparison_operator="LessThanOrEqualToThreshold",
            metric_name="CPUUtilization",
            namespace="AWS/ECS",
            period=120,
            statistic="Maximum",
            threshold=ecs_low_cpu_threshold,
            alarm_description="ECS CPU above threshold",
            dimensions=[
                cloudwatch.CfnAlarm.DimensionProperty(
                    name="ClusterName", value=cluster.cluster_name
                ),
                cloudwatch.CfnAlarm.DimensionProperty(
                    name="ServiceName",
                    value=self.ecs_service.attr_name,
                ),
            ],
            alarm_actions=[cpu_low_metric_policy.attr_id],
            evaluation_periods=1,
        )
