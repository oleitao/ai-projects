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
            "aws": {"type": "object"},
            "network": {"type": "object"},
            "compute": {"type": "object"},
            "data": {"type": "object"},
            "security": {"type": "object"},
            "tags": {"type": "object"},
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
                    "db_instance_class": {"type": "string"},
                    "db_allocated_storage": {"type": "number"},
                    "ec2_instance_type": {"type": "string"},
                },
            }
        },
    }
