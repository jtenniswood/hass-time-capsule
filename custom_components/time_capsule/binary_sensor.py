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
from .const import CONF_ENTITY_KEY, DOMAIN
from .entity import TimeCapsuleEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Expose SSH connectivity even when the poll fails."""
    async_add_entities(
        [TimeCapsuleConnection(entry.runtime_data, entry.data[CONF_ENTITY_KEY])]
    )


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
