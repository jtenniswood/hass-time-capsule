"""Sensor entities for a modded Time Capsule: envstat, SMART, and disk usage.

Set up from the UI (Settings -> Devices & Services -> Add Integration ->
Time Capsule Sensors); see config_flow.py. Exposes every degC envstat
reading (other than T_hdd, which this hardware never populates) as a
temperature sensor, the fan RPM reading as a fan-speed sensor, every SMART
attribute as its own sensor, one overall SMART pass/fail sensor, and the
internal drive's total, used, and free space plus percentages used and free.
Which envstat sensors show up is driven entirely by what envstat reports,
not a hardcoded list; same for the SMART attributes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util.dt import parse_datetime

from . import TimeCapsuleCoordinator
from .const import (
    CONF_ENTITY_KEY,
    DOMAIN,
    FRIENDLY_NAMES,
    HARDWARE_CHECKS,
    UNIT_FAN_RPM,
    UNIT_TEMPERATURE,
)
from .entity import TimeCapsuleEntity
from .smart import SmartAttribute

DISK_METRIC_NAMES = {
    "total": "Disk Total",
    "used": "Disk Used",
    "free": "Disk Free",
    "percent": "Disk Used Percentage",
    "free_percent": "Disk Free Percentage",
}

SMART_TEMPERATURE_DESCRIPTIONS = ("Temperature", "Airflow Temperature")
SMART_POWER_ON_HOURS_DESCRIPTION = "Power-on hours count"


def _friendly_name(label: str) -> str:
    return FRIENDLY_NAMES.get(label, label.replace("_", " ").strip())


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add fixed sensors and readings as they first arrive."""
    coordinator: TimeCapsuleCoordinator = entry.runtime_data
    device_key = entry.data[CONF_ENTITY_KEY]
    envstat_keys: set[str] = set()
    smart_ids: set[int] = set()

    @callback
    def async_add_new_readings() -> None:
        if not coordinator.last_update_success:
            return
        entities: list[SensorEntity] = []
        for key in coordinator.data.envstat:
            if key not in envstat_keys:
                entities.append(TimeCapsuleEnvstatSensor(coordinator, device_key, key))
                envstat_keys.add(key)
        for attr in coordinator.data.smart.attributes:
            if attr.id not in smart_ids:
                entities.append(
                    TimeCapsuleSmartAttributeSensor(coordinator, device_key, attr)
                )
                smart_ids.add(attr.id)
        if entities:
            async_add_entities(entities)

    entities: list[SensorEntity] = [
        TimeCapsuleSmartStatusSensor(coordinator, device_key),
        TimeCapsuleLastReadingSensor(coordinator, device_key),
    ]
    entities.extend(
        TimeCapsuleDiskSensor(coordinator, device_key, metric)
        for metric in DISK_METRIC_NAMES
    )
    async_add_entities(entities)
    async_add_new_readings()
    entry.async_on_unload(coordinator.async_add_listener(async_add_new_readings))


class TimeCapsuleEnvstatSensor(TimeCapsuleEntity, SensorEntity):
    """A single envstat reading (temperature or fan speed)."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: TimeCapsuleCoordinator, device_key: str, key: str
    ) -> None:
        super().__init__(coordinator, device_key)
        self._key = key

        reading = coordinator.data.envstat[key]
        self._attr_unique_id = f"{DOMAIN}_{device_key}_{key}"
        self._attr_name = _friendly_name(reading.label)

        if reading.unit == UNIT_TEMPERATURE:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        elif reading.unit == UNIT_FAN_RPM:
            self._attr_native_unit_of_measurement = UNIT_FAN_RPM
            self._attr_icon = "mdi:fan"

    @property
    def available(self) -> bool:
        return super().available and self._key in self.coordinator.data.envstat

    @property
    def native_value(self) -> Any:
        reading = self.coordinator.data.envstat.get(self._key)
        return reading.value if reading else None


class TimeCapsuleSmartAttributeSensor(TimeCapsuleEntity, SensorEntity):
    """A single row of the SMART attribute table (its raw value)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: TimeCapsuleCoordinator, device_key: str, attr: SmartAttribute
    ) -> None:
        super().__init__(coordinator, device_key)
        self._smart_id = attr.id
        self._attr_unique_id = f"{DOMAIN}_{device_key}_{attr.key}"
        self._attr_name = attr.description
        if attr.description.casefold() == "unknown":
            self._attr_name = f"Unknown SMART Attribute {attr.id}"

        if attr.description in SMART_TEMPERATURE_DESCRIPTIONS:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        elif attr.description == SMART_POWER_ON_HOURS_DESCRIPTION:
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.HOURS
        else:
            self._attr_icon = "mdi:harddisk"

    def _attribute(self):
        return next(
            a for a in self.coordinator.data.smart.attributes if a.id == self._smart_id
        )

    @property
    def available(self) -> bool:
        return super().available and any(
            a.id == self._smart_id for a in self.coordinator.data.smart.attributes
        )

    @property
    def native_value(self) -> Any:
        return self._attribute().raw if self.available else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self.available:
            return None
        attr = self._attribute()
        return {
            "normalized_value": attr.value,
            "threshold": attr.thresh,
            "critical": attr.critical,
            "collect": attr.collect,
            "reliability": attr.reliability,
        }


class TimeCapsuleSmartStatusSensor(TimeCapsuleEntity, SensorEntity):
    """Overall SMART pass/fail, derived from the critical attributes' thresholds."""

    def __init__(self, coordinator: TimeCapsuleCoordinator, device_key: str) -> None:
        super().__init__(coordinator, device_key)
        self._attr_unique_id = f"{DOMAIN}_{device_key}_smart_status"
        self._attr_name = "SMART Status"

    @property
    def native_value(self) -> str:
        return self.coordinator.data.smart.status

    @property
    def icon(self) -> str:
        return (
            "mdi:harddisk-alert"
            if not self.coordinator.data.smart.healthy
            else "mdi:harddisk"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        smart = self.coordinator.data.smart
        return {
            "failed_attributes": [a.description for a in smart.failed_attributes],
        }


class TimeCapsuleDiskSensor(TimeCapsuleEntity, SensorEntity):
    """Capacity and usage sensors for the internal drive."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self, coordinator: TimeCapsuleCoordinator, device_key: str, metric: str
    ) -> None:
        super().__init__(coordinator, device_key)
        self._metric = metric
        self._attr_unique_id = f"{DOMAIN}_{device_key}_disk_{metric}"
        self._attr_name = DISK_METRIC_NAMES[metric]

        if metric in ("percent", "free_percent"):
            self._attr_native_unit_of_measurement = PERCENTAGE
        else:
            self._attr_device_class = SensorDeviceClass.DATA_SIZE
            self._attr_native_unit_of_measurement = UnitOfInformation.BYTES
            self._attr_suggested_unit_of_measurement = UnitOfInformation.TERABYTES
            self._attr_suggested_display_precision = 1

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.disk is not None

    @property
    def native_value(self) -> Any:
        disk = self.coordinator.data.disk
        if disk is None:
            return None
        return {
            "total": disk.total_bytes,
            "used": disk.used_bytes,
            "free": disk.free_bytes,
            "percent": disk.use_percent,
            "free_percent": max(0, 100 - disk.use_percent),
        }[self._metric]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        disk = self.coordinator.data.disk
        if disk is None:
            return None
        return {"filesystem": disk.filesystem, "mounted_on": disk.mounted_on}


class TimeCapsuleLastReadingSensor(TimeCapsuleEntity, SensorEntity, RestoreEntity):
    """Timestamp of the latest usable reading, retained through connection loss."""

    _attr_name = "Last Successful Reading"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: TimeCapsuleCoordinator, device_key: str) -> None:
        super().__init__(coordinator, device_key)
        self._attr_unique_id = f"{DOMAIN}_{device_key}_last_reading"

    @property
    def available(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        previous = await self.async_get_last_state()
        if previous is None:
            return
        saved = previous.attributes.get("last_success_by_check", {})
        for check in HARDWARE_CHECKS:
            value = saved.get(check)
            if isinstance(value, str) and (timestamp := parse_datetime(value)):
                self.coordinator.last_success.setdefault(check, timestamp)

    @property
    def native_value(self) -> datetime | None:
        return max(self.coordinator.last_success.values(), default=None)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        checks = HARDWARE_CHECKS
        last_success = {
            check: self.coordinator.last_success[check].isoformat()
            for check in checks
            if check in self.coordinator.last_success
        }
        return {
            "last_success_by_check": last_success,
            "failed_checks": sorted(self.coordinator.data.errors)
            if super().available
            else list(checks),
        }
