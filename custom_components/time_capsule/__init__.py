"""The Time Capsule Sensors integration.

Config-entry based (see config_flow.py) -- one entry per Time Capsule, each
backed by a single coordinator shared by all of its sensors so envstat and
SMART status are only fetched once per poll regardless of how many readings
they produce between them.
"""

from __future__ import annotations

import logging
from functools import partial

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import TimeCapsuleConnectionError, TimeCapsuleData, fetch_time_capsule_data
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Time Capsule entry: create its coordinator and load sensor.py."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    include_name = True

    async def _async_update() -> TimeCapsuleData:
        try:
            return await hass.async_add_executor_job(
                partial(
                    fetch_time_capsule_data,
                    host,
                    port,
                    username,
                    password,
                    include_name=include_name,
                )
            )
        except TimeCapsuleConnectionError as err:
            raise UpdateFailed(str(err)) from err

    coordinator: DataUpdateCoordinator[TimeCapsuleData] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN} ({host})",
        update_method=_async_update,
        update_interval=DEFAULT_SCAN_INTERVAL,
    )
    await coordinator.async_config_entry_first_refresh()
    include_name = False

    registry = dr.async_get(hass)
    identifiers = {(DOMAIN, host)}
    previous_name = next(
        (
            device.name
            for device in dr.async_entries_for_config_entry(registry, entry.entry_id)
            if (DOMAIN, host) in device.identifiers
        ),
        None,
    )
    base_station_name = coordinator.data.base_station_name

    # Replace automatic titles while respecting titles chosen in Home Assistant.
    if base_station_name and entry.title in (f"Time Capsule ({host})", previous_name):
        hass.config_entries.async_update_entry(entry, title=base_station_name)

    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers=identifiers,
        name=base_station_name or previous_name or "Time Capsule",
        manufacturer="Apple",
        model="Apple Time Capsule",
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Time Capsule entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload after the options flow updates connection details."""
    await hass.config_entries.async_reload(entry.entry_id)
