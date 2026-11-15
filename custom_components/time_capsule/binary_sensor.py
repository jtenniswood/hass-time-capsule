"""Connection status for Time Capsules."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TimeCapsuleCoordinator
from .const import CONF_ENTITY_KEY, CONF_MONITOR_SMB, CONF_SMB_SHARE, DOMAIN
from .entity import TimeCapsuleEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Expose SSH connectivity even when the poll fails."""
    coordinator = entry.runtime_data
    key = entry.data[CONF_ENTITY_KEY]
    entities = [
        TimeCapsuleConnection(coordinator, key),
        TimeCapsuleStorageCheck(coordinator, key, "volume_mounted", "Backup Volume Mounted"),
    ]
    if entry.options.get(CONF_MONITOR_SMB):
        entities.append(
            TimeCapsuleStorageCheck(coordinator, key, "smb_port_open", "SMB Port Open")
        )
        if entry.options.get(CONF_SMB_SHARE):
            entities.append(
                TimeCapsuleStorageCheck(
                    coordinator, key, "smb_share_accessible", "SMB Share Accessible"
                )
            )
    async_add_entities(entities)


class TimeCapsuleConnection(TimeCapsuleEntity, BinarySensorEntity):
    """Whether the integration could connect and authenticate over SSH."""

    _attr_name = "SSH Connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: TimeCapsuleCoordinator, device_key: str) -> None:
        super().__init__(coordinator, device_key)
        self._attr_unique_id = f"{DOMAIN}_{device_key}_ssh_connected"

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return super().available


class TimeCapsuleStorageCheck(TimeCapsuleEntity, BinarySensorEntity):
    """Report the mount, SMB port, and authenticated share independently."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: TimeCapsuleCoordinator, device_key: str, key: str, name: str
    ) -> None:
        super().__init__(coordinator, device_key)
        self._check = key
        self._attr_unique_id = f"{DOMAIN}_{device_key}_{key}"
        self._attr_name = name
        if key != "volume_mounted":
            self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def available(self) -> bool:
        if self._check == "volume_mounted":
            return super().available
        return self.coordinator.last_update_success and self.coordinator.data.smb is not None

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if self._check == "volume_mounted":
            return data.volume_mounted
        if data.smb is None:
            return None
        if self._check == "smb_port_open":
            return data.smb.port_open
        return data.smb.share_accessible
