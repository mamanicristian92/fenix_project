
import json
from pathlib import Path

from botocore.exceptions import ClientError
from fenix.config.settings import client


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "data" / "inventory.json"


def inspect_instance(ec2, resource):
    instance_id = resource["id"]

    response = ec2.describe_instances(InstanceIds=[instance_id])
    instances = [
        instance
        for reservation in response["Reservations"]
        for instance in reservation["Instances"]
    ]

    print("\n--- EC2: node-01 ---")
    print(f"ID: {instance_id}")

    if not instances:
        print("Instancia no encontrada")
        return

    instance = instances[0]
    print(f"Estado: {instance['State']['Name']}")

    tags = {
        tag["Key"]: tag["Value"]
        for tag in instance.get("Tags", [])
    }
    print(f"Tags: {tags}")


def inspect_bucket(s3, resource):
    bucket_name = resource["id"]

    print("\n--- S3: bucket-01 ---")
    print(f"Nombre: {bucket_name}")

    try:
        response = s3.get_bucket_tagging(Bucket=bucket_name)
        tags = {
            tag["Key"]: tag["Value"]
            for tag in response["TagSet"]
        }
    except ClientError as error:
        code = error.response["Error"]["Code"]

        if code == "NoSuchTagSet":
            tags = {}
        else:
            raise

    print(f"Tags: {tags}")
    print(f"Owner presente: {'Owner' in tags}")


def main():
    with open(INVENTORY_PATH, encoding="utf-8") as file:
        inventory = json.load(file)

    ec2 = client("ec2")
    s3 = client("s3")

    print("===== ESTADO DE LOS RECURSOS =====")

    inspect_instance(ec2, inventory["node-01"])
    inspect_bucket(s3, inventory["bucket-01"])

    print("\n==================================")


if __name__ == "__main__":
    main()
