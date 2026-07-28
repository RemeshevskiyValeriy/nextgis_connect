from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class StorageLease:
    """Represent an active storage lease."""

    entry_id: int
    owner: str
    operation_id: str
    created_at: datetime
    expires_at: Optional[datetime]
