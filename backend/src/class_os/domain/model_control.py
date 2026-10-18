"""Closed technical configuration commands. No secret or universal settings JSON."""
from dataclasses import asdict, dataclass
from uuid import UUID

from .model_configuration import ModelConfiguration, Protocol


@dataclass(frozen=True)
class ModelControl:
    command: str
    candidate_id: UUID
    expected_version: int
    protocol: str | None = None
    model: str | None = None
    base_url: str | None = None

    def __post_init__(self):
        if (self.command not in ("model_configuration.save", "model_configuration.clear")
                or type(self.candidate_id) is not UUID or type(self.expected_version) is not int
                or not 0 <= self.expected_version < 2147483647):
            raise ValueError("Invalid model control")
        if self.command.endswith(".save"):
            ModelConfiguration(Protocol(self.protocol), self.model, self.base_url)
        elif any(value is not None for value in (self.protocol, self.model, self.base_url)):
            raise ValueError("Invalid model clear")

    def canonical(self):
        return {key: str(value) if isinstance(value, UUID) else value for key, value in asdict(self).items()}
