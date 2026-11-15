"""Poll each Time Capsule over one shared SSH connection."""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.dt import utcnow

from .client import (
    TimeCapsuleAuthError,
    TimeCapsuleConnectionError,
    TimeCapsuleData,
    fetch_time_capsule_data,
)
from .const import CONF_ENTITY_KEY, CONF_SSH_FINGERPRINT, DEFAULT_SCAN_INTERVAL, DOMAIN
from .smart import SmartStatus

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


class TimeCapsuleCoordinator(DataUpdateCoordinator[TimeCapsuleData]):
    """Poll the Capsule and remember when each check last returned usable data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} ({entry.data[CONF_HOST]})",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.entry = entry
        self.last_success: dict[str, datetime] = {}

    async def _async_update_data(self) -> TimeCapsuleData:
        data = self.entry.data
        try:
            result = await self.hass.async_add_executor_job(
                fetch_time_capsule_data,
                data[CONF_HOST],
                data[CONF_PORT],
                data[CONF_USERNAME],
                data[CONF_PASSWORD],
                data.get(CONF_SSH_FINGERPRINT),
            )
        except TimeCapsuleAuthError as err:
            raise ConfigEntryAuthFailed from err
        except TimeCapsuleConnectionError as err:
            if self.data is None:
                # Install diagnostic entities even when HA starts while the Capsule is offline.
                return TimeCapsuleData(
                    envstat={},
                    smart=SmartStatus(None, None, ()),
                    disk=None,
                    fingerprint=None,
                    errors={},
                    connected=False,
                )
            raise UpdateFailed(str(err)) from err

        if (
            self.entry.data is data
            and CONF_SSH_FINGERPRINT not in data
            and result.has_readings
        ):
            self.hass.config_entries.async_update_entry(
                self.entry, data={**data, CONF_SSH_FINGERPRINT: result.fingerprint}
            )

        now = utcnow()
        for check in result.successful_checks:
            self.last_success[check] = now
        return result


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Freeze the identity used by existing devices, automations and history."""
    if entry.version == 1:
        hass.config_entries.async_update_entry(
            entry,
            version=2,
            data={**entry.data, CONF_ENTITY_KEY: entry.data[CONF_HOST]},
        )
    return entry.version == 2


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one coordinator and its entities."""
    coordinator = TimeCapsuleCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload this Time Capsule."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
