"""Import Module."""
import aws_cdk as core
from constructs import Construct
from aws_cdk import (
    Stack,
    aws_sns as sns,
    aws_sqs as sqs,
    aws_sns_subscriptions as subs,
    aws_iam as iam,
)

from helper import config


class APISUBS_Stack(Stack):
    """Class to create API Service SNS Subscription to another SQS Queue"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        api_topic_arn,
        account_event_queue_arn,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Declare vars
        conf = config.Config(self.node.try_get_context("environment"))
        project_name = conf.get("project_name")
        stage = conf.get("stage")
        service_name = conf.get("api_service_name")
        # create sns subcription
        sns_topic = sns.Topic.from_topic_arn(self, "sns-topic", api_topic_arn)
        sqs_queue = sqs.Queue.from_queue_arn(self, "sqs-queue", account_event_queue_arn)
        sqs_queue_url = sqs.Queue.from_queue_arn(
            self, "sqs-queue-url", account_event_queue_arn
        ).queue_url

        sns_topic.add_subscription(subs.SqsSubscription(sqs_queue))

        policy = sqs.QueuePolicy(
            self,
            f"{service_name}-QueuePolicy",
            queues=[sqs_queue],
        )

        policy.document.add_statements(
            iam.PolicyStatement(
                actions=["SQS:SendMessage"],
                effect=iam.Effect.ALLOW,
                conditions={"ArnEquals": {"aws:SourceArn": api_topic_arn}},
                resources=[account_event_queue_arn],
                sid=f"allow-{api_topic_arn}",
            )
        )
        policy.node.add_dependency(sns_topic)
