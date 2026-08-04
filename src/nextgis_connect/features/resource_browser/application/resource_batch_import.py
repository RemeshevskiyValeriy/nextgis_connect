from dataclasses import dataclass
from typing import Hashable, Optional, Protocol, Tuple


class ResourceImportCancelledError(Exception):
    """Stop batch resource import after an explicit user cancellation."""


@dataclass(frozen=True)
class ResourceAddingErrorContext:
    """Describe a resource that failed during a batch import."""

    display_name: str
    insertion_id: Optional[Hashable] = None
    resource_ids: Tuple[int, ...] = ()
    resource_url: Optional[str] = None


class ResourceBatchImportInteraction(Protocol):
    """Define user decisions required by the batch import workflow."""

    def select_default_style(
        self,
        title: str,
        index: object,
        resource_model: object,
    ) -> int:
        """Return the selected style resource ID or cancel the import."""

    def should_skip_wfs_with_z(self) -> bool:
        """Return whether WFS layers with Z geometry must be skipped."""

    def should_skip_after_error(
        self,
        error: Exception,
        context: ResourceAddingErrorContext,
        can_skip: bool,
    ) -> bool:
        """Return whether a failed resource must be skipped."""
