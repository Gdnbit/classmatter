"""Small, dependency-free wire contract for untrusted message candidates."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re


class ConnectorError(Exception):
    """Only fixed reason codes may cross the worker/CLI boundary."""


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def label(value: object, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ConnectorError("invalid_input")
    if any(ord(c) < 32 for c in value):
        raise ConnectorError("invalid_input")
    return value


@dataclass(frozen=True)
class Scope:
    provider: str
    account: str
    chat: str

    def __post_init__(self):
        if self.provider not in PRESETS:
            raise ConnectorError("unknown_provider")
        label(self.account)
        label(self.chat)
        if self.provider == "replica" and (
            not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", self.account) or self.account in {".", ".."}
        ):
            raise ConnectorError("invalid_account_directory")

    @property
    def key(self) -> str:
        return digest(asdict(self))


@dataclass(frozen=True)
class Message:
    source_id: str
    sender: str | None
    text: str
    timestamp: str | None
    kind: str
    evidence: str

    def __post_init__(self):
        label(self.source_id, 1024)
        if not isinstance(self.text, str) or len(self.text) > 200_000:
            raise ConnectorError("invalid_message")
        if self.sender is not None:
            label(self.sender, 1024)
        if self.timestamp is not None:
            label(self.timestamp, 128)
        label(self.kind, 64)
        if self.evidence not in {"visual-inference", "uia-observation", "local-db-row"}:
            raise ConnectorError("invalid_evidence")


@dataclass(frozen=True)
class Page:
    messages: tuple[Message, ...]
    coverage: str
    # Exhaustion is an observation about this accessible source, never cloud completeness.
    exhausted: bool | None

    def __post_init__(self):
        if self.coverage not in {"visible-only", "requested-window", "paginated-local"}:
            raise ConnectorError("upstream_contract_changed")
        if self.exhausted is not None and type(self.exhausted) is not bool:
            raise ConnectorError("upstream_contract_changed")
        if not isinstance(self.messages, tuple) or not all(isinstance(m, Message) for m in self.messages):
            raise ConnectorError("upstream_contract_changed")


PRESETS = {
    "usechat": {"route": "visible-window", "history": "visible-only",
                "model_required": True, "send": True, "license": "MIT"},
    "pyweixin": {"route": "uia", "history": "requested-window",
                 "model_required": False, "send": True, "license": "LGPL-version-review-required"},
    "replica": {"route": "local-db", "history": "paginated-local",
                "model_required": False, "send": False, "license": "Apache-2.0"},
    "wxautox4": {"route": "uia-commercial", "history": "visible-only",
                 "model_required": False, "send": True, "license": "vendor-activation"},
}
