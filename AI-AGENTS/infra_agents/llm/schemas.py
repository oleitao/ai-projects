from __future__ import annotations

from typing import Any


def requirements_spec_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["cloud", "region", "env", "aws", "network", "compute", "data", "security", "tags"],
        "properties": {
            "cloud": {"type": "string", "enum": ["aws"]},
            "region": {"type": "string"},
            "env": {"type": "string", "enum": ["dev", "staging", "prod"]},
            "aws": {
                "type": "object",
                "required": [
                    "account_id",
                    "profile",
                    "backend_bucket",
                    "backend_dynamodb_table",
                    "backend_key_prefix",
                ],
                "properties": {
                    "account_id": {"type": "string"},
                    "profile": {"type": "string"},
                    "backend_bucket": {"type": "string"},
                    "backend_dynamodb_table": {"type": "string"},
                    "backend_key_prefix": {"type": "string"},
                },
            },
            "network": {
                "type": "object",
                "required": ["vpc_cidr", "public_subnets", "private_subnets"],
                "properties": {
                    "vpc_cidr": {"type": "string"},
                    "public_subnets": {"type": "array", "items": {"type": "string"}},
                    "private_subnets": {"type": "array", "items": {"type": "string"}},
                },
            },
            "compute": {
                "type": "object",
                "required": ["type", "sizing", "autoscaling"],
                "properties": {
                    "type": {"type": "string", "enum": ["ecs", "eks", "ec2"]},
                    "sizing": {"type": "string"},
                    "autoscaling": {"type": "boolean"},
                },
            },
            "data": {
                "type": "object",
                "required": ["rds", "engine", "multi_az", "backups"],
                "properties": {
                    "rds": {"type": "boolean"},
                    "engine": {"type": "string", "enum": ["postgres", "mysql"]},
                    "multi_az": {"type": "boolean"},
                    "backups": {"type": "boolean"},
                },
            },
            "security": {
                "type": "object",
                "required": ["encryption", "public_access"],
                "properties": {
                    "encryption": {"type": "boolean"},
                    "public_access": {"type": "boolean"},
                },
            },
            "tags": {
                "type": "object",
                "required": ["owner", "cost_center"],
                "properties": {
                    "owner": {"type": "string"},
                    "cost_center": {"type": "string"},
                },
            },
        },
    }


def planner_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "modules": {
                "type": "array",
                "items": {"type": "string"},
            },
            "notes": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    }


def generator_overrides_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "tfvars_overrides": {
                "type": "object",
                "properties": {
                    "db_instance_class": {
                        "type": "string",
                        "enum": ["db.t3.micro", "db.t3.small", "db.t3.medium"],
                    },
                    "db_allocated_storage": {
                        "type": "number",
                        "minimum": 20,
                        "maximum": 1024,
                    },
                    "ec2_instance_type": {
                        "type": "string",
                        "enum": ["t3.micro", "t3.small", "t3.medium", "t3.large"],
                    },
                },
            }
        },
    }


def schema_by_name(name: str) -> dict[str, Any]:
    builders = {
        "InfrastructureSpec": requirements_spec_schema,
        "PlannerDecision": planner_schema,
        "GeneratorOverrides": generator_overrides_schema,
    }
    builder = builders.get(name)
    return builder() if builder else {"type": "object"}
