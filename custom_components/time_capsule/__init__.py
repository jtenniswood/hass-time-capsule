"""Poll each Time Capsule over one shared SSH connection."""

from __future__ import annotations

import logging
from asyncio import gather
from dataclasses import replace
from datetime import datetime
from functools import partial

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
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.dt import utcnow

from .client import (
    TimeCapsuleAuthError,
    TimeCapsuleConnectionError,
    TimeCapsuleData,
    fetch_time_capsule_data,
)
from .const import (
    CONF_ENTITY_KEY,
    CONF_MONITOR_SMB,
    CONF_SMB_PASSWORD,
    CONF_SMB_SHARE,
    CONF_SMB_USERNAME,
    CONF_SSH_FINGERPRINT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .smb import probe_smb
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
        self._read_name = True

    async def _async_update_data(self) -> TimeCapsuleData:
        options = self.entry.options
        if options.get(CONF_MONITOR_SMB):
            hardware, smb = await gather(
                self._async_read_hardware(),
                self.hass.async_add_executor_job(
                    probe_smb,
                    self.entry.data[CONF_HOST],
                    options.get(CONF_SMB_SHARE, ""),
                    options.get(CONF_SMB_USERNAME, ""),
                    options.get(CONF_SMB_PASSWORD, ""),
                ),
            )
            return replace(hardware, smb=smb)
        return await self._async_read_hardware()

    async def _async_read_hardware(self) -> TimeCapsuleData:
        data = self.entry.data
        try:
            result = await self.hass.async_add_executor_job(
                partial(
                    fetch_time_capsule_data,
                    data[CONF_HOST],
                    data[CONF_PORT],
                    data[CONF_USERNAME],
                    data[CONF_PASSWORD],
                    data.get(CONF_SSH_FINGERPRINT),
                    include_name=self._read_name,
                )
            )
        except TimeCapsuleAuthError as err:
            raise ConfigEntryAuthFailed from err
        except TimeCapsuleConnectionError as err:
            if self.data is None or self.data.connected:
                _LOGGER.warning("Time Capsule SSH unavailable: %s", err)
            return TimeCapsuleData(
                envstat={},
                smart=SmartStatus(None, None, ()),
                disk=None,
                fingerprint=None,
                errors={},
                connected=False,
            )

        if self.data is not None and not self.data.connected:
            _LOGGER.info("Time Capsule SSH connection restored")

        if self.entry.data is data:
            if self._read_name and result.connected:
                self._read_name = False
                _async_register_device(self.hass, self.entry, result.base_station_name)
            if CONF_SSH_FINGERPRINT not in data and result.has_readings:
                self.hass.config_entries.async_update_entry(
                    self.entry, data={**data, CONF_SSH_FINGERPRINT: result.fingerprint}
                )

        now = utcnow()
        for check in result.successful_checks:
            self.last_success[check] = now
        return result


def _async_register_device(
    hass: HomeAssistant, entry: ConfigEntry, base_station_name: str | None
) -> None:
    """Register the stable device and apply any name read from AirPort Utility."""
    registry = dr.async_get(hass)
    identifier = (DOMAIN, entry.data[CONF_ENTITY_KEY])
    previous_name = next(
        (
            device.name
            for device in dr.async_entries_for_config_entry(registry, entry.entry_id)
            if identifier in device.identifiers
        ),
        None,
    )
    generic_title = f"Time Capsule ({entry.data[CONF_HOST]})"
    if base_station_name and entry.title in (generic_title, previous_name):
        hass.config_entries.async_update_entry(entry, title=base_station_name)

    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={identifier},
        name=base_station_name or previous_name or "Time Capsule",
        manufacturer="Apple",
        model="Apple Time Capsule",
    )


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
    if not coordinator.data.connected:
        _async_register_device(hass, entry, None)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload this Time Capsule."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
