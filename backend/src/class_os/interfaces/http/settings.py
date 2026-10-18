"""Deliberately limited synthetic runtime configuration; no .env loading."""
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class Settings:
    mode: str = "synthetic-development"
    bind_host: str = "127.0.0.1"
    model_provider: str = "fake"
    port: int = 8000
    model_api_bases: tuple[str, ...] = ()

    def __post_init__(self):
        if (self.mode != "synthetic-development" or self.bind_host != "127.0.0.1"
                or self.model_provider != "fake" or type(self.port) is not int
                or not 1024 <= self.port <= 65535):
            raise ValueError("Invalid backend settings")
        if type(self.model_api_bases) is not tuple or len(self.model_api_bases) > 4:
            raise ValueError("Invalid model API allowlist")
        from class_os.domain.model_configuration import ModelConfiguration, Protocol
        for url in self.model_api_bases:
            ModelConfiguration(Protocol.CHAT, "configuration-check", url)

    @classmethod
    def from_env(cls, env: Mapping[str, str]):
        try:
            return cls(
                mode=env.get("CLASS_OS_MODE", "synthetic-development"),
                bind_host=env.get("CLASS_OS_HOST", "127.0.0.1"),
                model_provider=env.get("CLASS_OS_MODEL_PROVIDER", "fake"),
                port=int(env.get("CLASS_OS_PORT", "8000")),
            )
        except (ValueError, TypeError):
            raise ValueError("Invalid backend settings") from None
