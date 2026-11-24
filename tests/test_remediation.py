import pytest

from fenix.services import remediation
from fenix.utils.errors import RetryableError


def test_ec2_verifies_running_after_start(monkeypatch):
    class FakeEC2:
        states = iter(["stopped", "running"])

        def describe_instances(self, **kwargs):
            return {
                "Reservations": [{
                    "Instances": [{"State": {"Name": next(self.states)}}]
                }]
            }

        def start_instances(self, **kwargs):
            pass

    monkeypatch.setattr(remediation, "client", lambda service: FakeEC2())

    result = remediation.repair(
        {"type": "ec2", "id": "i-test"}, "instance.stopped"
    )

    assert result == "repaired"


def test_ec2_does_not_confirm_before_running(monkeypatch):
    class FakeEC2:
        states = iter(["stopped", "pending"])

        def describe_instances(self, **kwargs):
            return {
                "Reservations": [{
                    "Instances": [{"State": {"Name": next(self.states)}}]
                }]
            }

        def start_instances(self, **kwargs):
            pass

    monkeypatch.setattr(remediation, "client", lambda service: FakeEC2())

    with pytest.raises(RetryableError):
        remediation.repair(
            {"type": "ec2", "id": "i-test"}, "instance.stopped"
        )


def test_s3_preserves_tags_and_verifies_update(monkeypatch):
    class FakeS3:
        tags = {"Owner": "team-a", "Environment": "development"}

        def get_bucket_tagging(self, **kwargs):
            return {
                "TagSet": [
                    {"Key": key, "Value": value}
                    for key, value in self.tags.items()
                ]
            }

        def put_bucket_tagging(self, **kwargs):
            self.tags = {
                tag["Key"]: tag["Value"]
                for tag in kwargs["Tagging"]["TagSet"]
            }

    fake = FakeS3()
    monkeypatch.setattr(remediation, "client", lambda service: fake)

    result = remediation.repair(
        {
            "type": "s3",
            "id": "bucket-test",
            "expected_tags": {
                "Environment": "production",
                "Project": "Fenix"
            }
        },
        "bucket.tags.missing"
    )

    assert result == "repaired"
    assert fake.tags == {
        "Owner": "team-a",
        "Environment": "production",
        "Project": "Fenix"
    }


def test_s3_does_not_write_if_tags_are_correct(monkeypatch):
    class FakeS3:
        def get_bucket_tagging(self, **kwargs):
            return {
                "TagSet": [
                    {"Key": "Environment", "Value": "production"},
                    {"Key": "Project", "Value": "Fenix"}
                ]
            }

        def put_bucket_tagging(self, **kwargs):
            pytest.fail("No debería modificar las etiquetas")

    monkeypatch.setattr(remediation, "client", lambda service: FakeS3())

    result = remediation.repair(
        {
            "type": "s3",
            "id": "bucket-test",
            "expected_tags": {
                "Environment": "production",
                "Project": "Fenix"
            }
        },
        "bucket.tags.missing"
    )

    assert result == "already_ok"
