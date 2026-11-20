
import os
import boto3
from dotenv import load_dotenv

load_dotenv()

sqs = boto3.client(
    "sqs",
    endpoint_url=os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566"),
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    aws_access_key_id="test",
    aws_secret_access_key="test",
)

prefix = os.environ["QUEUE_PREFIX"]
dlq_name = f"{prefix}-dlq"

response = sqs.get_queue_url(QueueName=dlq_name)
dlq_url = response["QueueUrl"]

attributes = sqs.get_queue_attributes(
    QueueUrl=dlq_url,
    AttributeNames=["ApproximateNumberOfMessages"],
)

count = attributes["Attributes"]["ApproximateNumberOfMessages"]

print(f"DLQ: {dlq_name}")
print(f"Mensajes disponibles: {count}")
