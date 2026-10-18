"""Explicit non-durable provider activation. SDK owns all model/tool loops."""
import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone

import anyio
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from class_os.domain.model_configuration import ConfigurationRejected, ModelConfiguration, Protocol
from .model_provider import configured_client, model_for_configuration
from .agent import fake_model


class ModelController:
    def __init__(self, query, secrets, runtime, *, allowed_bases=(), client_factory=configured_client,
                 clock=lambda: datetime.now(timezone.utc)):
        self.query, self.secrets, self.runtime = query, secrets, runtime
        self.allowed_bases, self.client_factory, self.clock = tuple(allowed_bases), client_factory, clock
        self._proofs, self._enabled, self._attempts = {}, {}, {}
        self._testing = False

    async def _row(self, credentials, action="model.config.read"):
        return await anyio.to_thread.run_sync(lambda: self.query.model_configuration(credentials, action=action))

    @staticmethod
    def signature(row):
        return (row["candidate_id"], row["version"]) if row else (None, 0)

    @staticmethod
    def profile(row):
        if not row or row["sealed"] is None:
            raise ConfigurationRejected()
        return ModelConfiguration(Protocol(row["protocol"]), row["model"], row["base_url"])

    def permitted(self, row):
        return bool(row and row["sealed"] is not None and row["base_url"] in self.allowed_bases)

    def label(self, credentials):
        return "configured-api" if credentials[3] in self._enabled else "synthetic-function-model"

    def proof_key(self, credentials, row):
        return (self.secrets.binding(credentials), self.signature(row))

    def tested(self, credentials, row):
        expiry = self._proofs.get(self.proof_key(credentials, row))
        return expiry is not None and self.clock() < expiry

    async def status(self, credentials):
        row = await self._row(credentials)
        enabled = self._enabled.get(credentials[3])
        return {"schema_version": "class-os.model-status.v1", "storage_available": True,
                "version": row["version"] if row else 0,
                "candidate_id": str(row["candidate_id"]) if row else None,
                "configuration": {"protocol": row["protocol"], "model": row["model"], "base_url": row["base_url"]} if row and row["sealed"] else None,
                "key_configured": bool(row and row["sealed"]), "network_permitted": self.permitted(row),
                "test_passed": self.tested(credentials, row),
                "mode": "offline" if enabled is None else "configured-api" if enabled == self.signature(row) and row["sealed"] else "stale"}

    async def stage(self, credentials, profile, key, version):
        row = await self._row(credentials)
        if version != (row["version"] if row else 0):
            raise ConfigurationRejected()
        return self.secrets.stage(credentials, profile, key, version)

    async def test(self, credentials, candidate, version, request_id):
        row = await self._row(credentials)
        if self.signature(row) != (candidate, version) or not self.permitted(row):
            raise ConfigurationRejected()
        binding = self.proof_key(credentials, row)
        now = self.clock()
        self._proofs = {k: v for k, v in self._proofs.items() if now < v}
        self._attempts = {k: v for k, v in self._attempts.items() if now < v[0]}
        identity = (binding, request_id)
        if identity in self._attempts:
            if self._attempts[identity][1] is None:
                raise ConfigurationRejected()
            return self._attempts[identity][1]
        if self._testing or self.runtime.active or len(self._attempts) >= 32 or len(self._proofs) >= 32:
            raise ConfigurationRejected()
        self._testing = True
        self._proofs.pop(binding, None)
        self._attempts[identity] = (now + timedelta(minutes=10), None)
        passed = False
        try:
            row = await self._row(credentials, "model.test.started")
            if self.signature(row) != (candidate, version):
                raise ConfigurationRejected()
            profile = self.profile(row)
            key = self.secrets.open(credentials[3], candidate, version, profile, bytes(row["sealed"]))
            called = False
            def class_os_probe() -> str:
                """Call this exactly once to validate this synthetic tool protocol."""
                nonlocal called
                if called:
                    raise ConfigurationRejected()
                called = True
                return "class-os-synthetic-probe-ok"
            async with asyncio.timeout(10):
                async with self.client_factory(profile, key) as client:
                    probe = Agent(model_for_configuration(profile, client), tools=[class_os_probe], retries=0,
                                  model_settings={"max_tokens": 1024})
                    probe.instrument = False
                    result = await probe.run("Synthetic connectivity test only: call class_os_probe once, then reply OK.",
                                             usage_limits=UsageLimits(request_limit=2, tool_calls_limit=1, total_tokens_limit=6000))
            if not called or result.response.state != "complete" or result.response.finish_reason in ("length", "content_filter", "error"):
                raise ConfigurationRejected()
            current = await self._row(credentials, "model.test.completed")
            if self.signature(current) != (candidate, version):
                raise ConfigurationRejected()
            self._proofs[binding] = self.clock() + timedelta(minutes=10)
            passed = True
        except asyncio.CancelledError:
            with suppress(Exception):
                await self._row(credentials, "model.test.failed")
            raise
        except Exception:
            self._proofs.pop(binding, None)
            with suppress(Exception):
                await self._row(credentials, "model.test.failed")
        finally:
            self._attempts[identity] = (self.clock() + timedelta(minutes=10), passed)
            self._testing = False
        return passed

    async def enable(self, credentials, candidate, version):
        row = await self._row(credentials)
        if not self.permitted(row) or self.signature(row) != (candidate, version) or not self.tested(credentials, row):
            raise ConfigurationRejected()
        current = await self._row(credentials, "model.enable")
        if self.signature(current) != (candidate, version) or self.runtime.active or self._testing or not self.tested(credentials, current):
            raise ConfigurationRejected()
        if credentials[3] not in self._enabled and len(self._enabled) >= 32:
            raise ConfigurationRejected()
        self.runtime.memory.clear()
        self._enabled[credentials[3]] = self.signature(current)

    async def disable(self, credentials):
        await self._row(credentials, "model.disable")
        if self.runtime.active or self._testing:
            raise ConfigurationRejected()
        self.runtime.memory.clear()
        self._enabled.pop(credentials[3], None)

    @asynccontextmanager
    async def context(self, credentials, request):
        selected = self._enabled.get(credentials[3])
        if selected is None:
            yield fake_model(request)
            return
        row = await self._row(credentials, "model.invoke")
        if self.signature(row) != selected or not self.permitted(row):
            raise ConfigurationRejected()
        profile = self.profile(row)
        key = self.secrets.open(credentials[3], row["candidate_id"], row["version"], profile, bytes(row["sealed"]))
        async with self.client_factory(profile, key) as client:
            yield model_for_configuration(profile, client)
            current = await self._row(credentials)
            if self.signature(current) != selected or self._enabled.get(credentials[3]) != selected:
                raise ConfigurationRejected()
