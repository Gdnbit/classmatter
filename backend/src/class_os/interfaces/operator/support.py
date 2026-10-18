"""Opt-in allowlisted technical metadata; never collects logs or credentials."""
from importlib.metadata import PackageNotFoundError, version
import os
import re
import sys
from typing import Annotated, Literal

from pydantic import Field, StrictBool, model_validator

from class_os.interfaces.http.contracts import WireModel
from .doctor import diagnose


class HealthChecks(WireModel):
    live: Literal["ok", "unavailable", "invalid_response"]
    ready: Literal["ok", "unavailable", "invalid_response", "not_ready"]


class HealthSummary(WireModel):
    schema_version: Literal["class-os.local-diagnostics.v1"]
    profile: Literal["synthetic-development"]
    checks: HealthChecks
    ready: StrictBool
    complete_operator_check: Literal[False]
    next_step: Literal["none", "start-local-api", "check-owned-database-and-explicit-migration", "check-local-service-contract"]

    @model_validator(mode="after")
    def coherent(self):
        ready = self.checks.live == self.checks.ready == "ok"
        next_step = ("none" if ready else "start-local-api" if self.checks.live == "unavailable" else
                     "check-owned-database-and-explicit-migration" if self.checks.ready == "not_ready" else
                     "check-local-service-contract")
        if self.ready != ready or self.next_step != next_step:
            raise ValueError("Incoherent health metadata")
        return self


Version = Annotated[str, Field(pattern=r"^(?:[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|unavailable|unverified)$", max_length=16)]


class Versions(WireModel):
    python: Version
    backend: Version
    pydantic_ai: Version
    openai: Version
    pydantic: Version
    fastapi: Version


class SupportReport(WireModel):
    schema_version: Literal["class-os.synthetic-support.v1"] = "class-os.synthetic-support.v1"
    profile: Literal["synthetic-development"] = "synthetic-development"
    scope: Literal["health-and-versions-only"] = "health-and-versions-only"
    platform: Literal["windows", "posix", "unknown"]
    build_identity: Literal["unverified"] = "unverified"
    versions_scope: Literal["operator-process-not-server"] = "operator-process-not-server"
    health: HealthSummary
    versions: Versions
    business_data_collected: Literal[False] = False
    secrets_collected: Literal[False] = False
    logs_collected: Literal[False] = False
    uploaded: Literal[False] = False
    complete_support_bundle: Literal[False] = False


def _version(distribution):
    try:
        value = version(distribution)
    except PackageNotFoundError:
        return "unavailable"
    except (ValueError, OSError):
        return "unverified"
    # No arbitrary metadata strings, local paths, vendor suffixes or exception
    # details enter a shareable report, even from damaged package metadata.
    return value if type(value) is str and len(value) <= 16 and re.fullmatch(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", value) else "unverified"


def collect(settings):
    health = HealthSummary.model_validate(diagnose(settings), strict=True)
    versions = Versions(python=".".join(map(str, sys.version_info[:3])),
                        backend=_version("class-os-backend"), pydantic_ai=_version("pydantic-ai-slim"),
                        openai=_version("openai"), pydantic=_version("pydantic"), fastapi=_version("fastapi"))
    return SupportReport(platform="windows" if os.name == "nt" else "posix" if os.name == "posix" else "unknown",
                         health=health, versions=versions)
