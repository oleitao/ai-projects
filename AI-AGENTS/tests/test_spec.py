import unittest

from infra_agents.contracts import InfrastructureSpec, SpecValidationError


class SpecValidationTests(unittest.TestCase):
    def test_spec_accepts_valid_payload(self):
        payload = {
            "cloud": "aws",
            "region": "eu-west-1",
            "env": "prod",
            "aws": {
                "account_id": "123456789012",
                "profile": "default",
                "backend_bucket": "tfstate-prod-123456789012",
                "backend_dynamodb_table": "tfstate-locks-prod",
                "backend_key_prefix": "infra-agents",
            },
            "compute": {"type": "ecs", "sizing": "small", "autoscaling": True},
            "data": {"rds": True, "engine": "postgres", "multi_az": True, "backups": True},
            "security": {"encryption": True, "public_access": False},
            "tags": {"owner": "team", "cost_center": "cc100"},
        }
        spec = InfrastructureSpec.from_dict(payload)
        self.assertEqual(spec.cloud, "aws")
        self.assertEqual(spec.aws.account_id, "123456789012")

    def test_spec_rejects_invalid_compute_type(self):
        payload = {
            "cloud": "aws",
            "compute": {"type": "lambda", "sizing": "small", "autoscaling": False},
            "tags": {"owner": "team", "cost_center": "cc100"},
        }
        with self.assertRaises(SpecValidationError):
            InfrastructureSpec.from_dict(payload)

    def test_spec_rejects_invalid_account_id(self):
        payload = {
            "cloud": "aws",
            "region": "eu-west-1",
            "env": "prod",
            "aws": {
                "account_id": "12345",
                "backend_bucket": "tfstate-prod-123456789012",
                "backend_dynamodb_table": "tfstate-locks-prod",
                "backend_key_prefix": "infra-agents",
            },
            "compute": {"type": "ecs", "sizing": "small", "autoscaling": True},
            "tags": {"owner": "team", "cost_center": "cc100"},
        }
        with self.assertRaises(SpecValidationError):
            InfrastructureSpec.from_dict(payload)


if __name__ == "__main__":
    unittest.main()
