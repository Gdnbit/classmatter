"""Small renderer port for derivatives of saved working documents, not facts."""
from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

ExportFormat = Literal['docx', 'pptx']
MEDIA = MappingProxyType({'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation'})
MAX_BYTES = 4 * 1024 * 1024


class ArtifactTooLarge(ValueError):
    pass


@dataclass(frozen=True)
class OfficeArtifact:
    content: bytes
    media_type: str
    filename: str


OfficeRenderer = Callable[[str, str, str, ExportFormat], OfficeArtifact]
