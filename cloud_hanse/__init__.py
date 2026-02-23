"""Cloud-Hanse: Drive-synchronisierte Wirtschaftssimulation."""

from .simulation import WorldSimulator

try:
    from .drive_sync import DriveSyncError, DriveWriteUnavailable, GoogleDriveWorldStateStore
except Exception:  # pragma: no cover - optional at import time
    DriveSyncError = RuntimeError
    DriveWriteUnavailable = RuntimeError
    GoogleDriveWorldStateStore = object  # type: ignore[assignment]

__all__ = [
    "DriveSyncError",
    "DriveWriteUnavailable",
    "GoogleDriveWorldStateStore",
    "WorldSimulator",
]
