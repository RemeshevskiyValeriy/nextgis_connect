from dataclasses import dataclass, field
from typing import List


@dataclass
class MigrationReport:
    """Describe storage migration results."""

    scanned_files: int = 0
    migrated_files: int = 0
    skipped_files: int = 0
    quarantined_files: int = 0
    blocked_files: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
