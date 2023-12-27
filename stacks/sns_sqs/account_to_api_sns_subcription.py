"""Import Module."""
from constructs import Construct
from aws_cdk import (
    Stack,
    aws_sns as sns,
    aws_sqs as sqs,
    aws_sns_subscriptions as subs,
    aws_iam as iam,
)

from helper import config


class AccountSUBS_Stack(Stack):
    """Class to create Account Service SNS Subscription to Another SQS queue"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        account_topic_arn,
        api_event_queue_arn,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Declare vars
        conf = config.Config(self.node.try_get_context("environment"))
        service_name = conf.get("api_service_name")
        # create sns subcription
        sns_topic = sns.Topic.from_topic_arn(self, "sns-topic", account_topic_arn)
        sqs_queue = sqs.Queue.from_queue_arn(self, "sqs-queue", api_event_queue_arn)

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
                conditions={"ArnEquals": {"aws:SourceArn": account_topic_arn}},
                resources=[api_event_queue_arn],
                sid=f"allow-{account_topic_arn}",
            )
        )
        policy.node.add_dependency(sns_topic)
