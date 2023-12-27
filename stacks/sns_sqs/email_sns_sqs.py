"""Import necessary CDK modules."""
import aws_cdk as core
from constructs import Construct
from aws_cdk import (
    Stack,
    aws_sns as sns,
    aws_sqs as sqs,
    aws_ssm as ssm,
)
from helper import config


class EmailSNSSQS_Stack(Stack):
    """Class to create Email Service SQSQueue"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Declare vars
        conf = config.Config(self.node.try_get_context("environment"))
        project_name = conf.get("project_name")
        stage = conf.get("stage")
        service_name = conf.get("email_service_name")
        is_sns_enabled = False
        # create sns topic
        if is_sns_enabled:
            self.sns_topic = sns.Topic(
                self,
                "SNSTopic",
                topic_name=f"{project_name}-{service_name}-event",
                display_name=f"{project_name}-{service_name}-event",
            )

            sns_topic_delivery_policy = {
                "http": {
                    "defaultHealthyRetryPolicy": {
                        "minDelayTarget": 20,
                        "maxDelayTarget": 20,
                        "numRetries": 3,
                        "numMaxDelayRetries": 0,
                        "numNoDelayRetries": 0,
                        "numMinDelayRetries": 0,
                        "backoffFunction": "linear",
                    },
                    "disableSubscriptionOverrides": False,
                }
            }
            self.sns_topic.node.default_child.add_property_override(
                "TopicDeliveryPolicy", sns_topic_delivery_policy
            )
            ssm.StringParameter(
                self,
                f"/${service_name}-SSM_SNS_TOPIC_ARN",
                parameter_name=f"/{service_name}/{stage}/AWS_SNS_EVENT_TOPIC_ARN",
                string_value=self.sns_topic.topic_arn,
            )
        # create sqs

        self.sqs_dlq_queue = sqs.Queue(
            self,
            f"/${service_name}-MainDLQQueue",
            queue_name=f"{project_name}-{service_name}-event-dlq",
            delivery_delay=core.Duration.seconds(30),
            max_message_size_bytes=262144,
            retention_period=core.Duration.seconds(345600),
            receive_message_wait_time=core.Duration.seconds(10),
            visibility_timeout=core.Duration.seconds(300),
            encryption=sqs.QueueEncryption.KMS_MANAGED,
            encryption_master_key=None,
        )
        ssm.StringParameter(
            self,
            f"/${service_name}-AWS_SQS_DLQ_URL",
            parameter_name=f"/{service_name}/{stage}/AWS_SQS_DLQ_URL",
            string_value=self.sqs_dlq_queue.queue_url,
        )

        self.sqs_event_queue = sqs.Queue(
            self,
            f"/${service_name}-EventQueue",
            queue_name=f"{project_name}-{service_name}-event-queue",
            delivery_delay=core.Duration.seconds(0),
            max_message_size_bytes=262144,
            retention_period=core.Duration.seconds(3600),
            receive_message_wait_time=core.Duration.seconds(0),
            visibility_timeout=core.Duration.seconds(300),
            encryption=sqs.QueueEncryption.KMS_MANAGED,
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=10, queue=self.sqs_dlq_queue
            ),
        )
        ssm.StringParameter(
            self,
            f"/${service_name}-AWS_SQS_QUEUE_URL",
            parameter_name=f"/{service_name}/{stage}/AWS_SQS_QUEUE_URL",
            string_value=self.sqs_event_queue.queue_url,
        )
