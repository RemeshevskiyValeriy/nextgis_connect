from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Tuple


@dataclass(frozen=True)
class ResourceImportWarning:
    """Store a user-facing non-fatal batch import warning."""

    message: str
    detail: Optional[str] = None


class ResourceBatchImportStatus(Enum):
    """Identify the terminal state of a batch import operation."""

    SUCCEEDED = auto()
    CANCELLED = auto()
    FAILED = auto()


@dataclass(frozen=True)
class ResourceBatchImportResult:
    """Return the observable outcome of a batch import operation."""

    status: ResourceBatchImportStatus
    added_layer_ids: Tuple[str, ...] = ()
    warnings: Tuple[ResourceImportWarning, ...] = ()

    @property
    def is_success(self) -> bool:
        return self.status == ResourceBatchImportStatus.SUCCEEDED
