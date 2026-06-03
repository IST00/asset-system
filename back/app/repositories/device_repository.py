"""Device repository — lookup + first-time insert."""

from __future__ import annotations

from app.models import Device
from app.repositories.base import BaseRepository


class DeviceRepository(BaseRepository[Device]):
    def __init__(self) -> None:
        super().__init__(Device)

    def find_by_device_id(self, device_id: str) -> Device | None:
        return self.find_one(Device.device_id == device_id)


device_repository = DeviceRepository()

__all__ = ["DeviceRepository", "device_repository"]
