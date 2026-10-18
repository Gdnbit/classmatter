"""Nonsecret model-adapter candidate, not business facts or endpoint admission."""
from dataclasses import dataclass
from enum import StrEnum
import re
from urllib.parse import urlsplit


class Protocol(StrEnum):
    CHAT = "chat-completions"
    RESPONSES = "responses"


class ConfigurationRejected(Exception):
    def __init__(self):
        super().__init__("Invalid model configuration")


@dataclass(frozen=True)
class ModelConfiguration:
    protocol: Protocol
    model: str
    base_url: str

    def __post_init__(self):
        if (type(self.protocol) is not Protocol or type(self.model) is not str
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,127}", self.model) is None
                or type(self.base_url) is not str or not 1 <= len(self.base_url) <= 512
                or any(ord(c) < 33 or ord(c) > 126 for c in self.base_url)):
            raise ConfigurationRejected()
        try:
            url = urlsplit(self.base_url)
            if (url.scheme not in ("https", "http") or not url.hostname
                    or url.username is not None or url.password is not None
                    or url.query or url.fragment or "?" in self.base_url or "#" in self.base_url
                    or re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*(?::[0-9]{1,5})?", url.netloc) is None
                    or re.fullmatch(r"(?:/[A-Za-z0-9_-]+)*/?", url.path) is None
                    or (url.port is not None and not 1 <= url.port <= 65535)
                    or (url.scheme == "http" and url.hostname != "127.0.0.1")):
                raise ConfigurationRejected()
        except (ValueError, TypeError):
            raise ConfigurationRejected() from None
