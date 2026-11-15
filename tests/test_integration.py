"""Exercise migration, polling and setup flows using Home Assistant Core."""

import unittest
from ipaddress import ip_address
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

try:
    from homeassistant.bootstrap import async_from_config_dict
except ModuleNotFoundError as err:
    if err.name != "homeassistant":
        raise
    raise unittest.SkipTest(
        "Install Home Assistant Core for the integration tests"
    ) from err

from homeassistant import loader
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from custom_components.time_capsule.client import (
    TimeCapsuleConnectionError,
    TimeCapsuleData,
    TimeCapsuleIdentityError,
    fetch_time_capsule_data,
)
from custom_components.time_capsule.const import (
    CONF_AIRPORT_MAC,
    CONF_ENTITY_KEY,
    CONF_SSH_FINGERPRINT,
    DF_COMMAND,
    DOMAIN,
    ENVSTAT_COMMAND,
    SMART_COMMAND,
)
from custom_components.time_capsule.df import parse_df
from custom_components.time_capsule.envstat import parse_envstat
from custom_components.time_capsule.smart import parse_smart_status

CONNECTION = {"host": "192.0.2.10", "port": 22, "username": "root", "password": "test"}
FINGERPRINT = "SHA256:fake-test-key"
ENVSTAT = "[tsensor0]\nT_internal: 45.32 degC"
SMART = "SMART supported, SMART enabled\n197 100 0 no online positive Current pending sector 0"
DF = "Filesystem 512-blocks Used Avail %Cap Mounted on\n/dev/dk2 10000 2500 7500 25% /Volumes/dk2"


def poll_result(*, no_disk=False):
    return TimeCapsuleData(
        envstat={reading.key: reading for reading in parse_envstat(ENVSTAT)},
        smart=parse_smart_status(SMART),
        disk=None if no_disk else parse_df(DF),
        fingerprint=FINGERPRINT,
        errors={"disk": "Disk offline"} if no_disk else {},
    )


def discovery(address, model="119"):
    ip = ip_address(address)
    return ZeroconfServiceInfo(
        ip_address=ip,
        ip_addresses=[ip],
        port=5009,
        hostname="Time-Capsule-Test.local.",
        type="_airport._tcp.local.",
        name="Time Capsule Test._airport._tcp.local.",
        properties={"waMA": f"02-00-00-00-00-01,raSt=0,syAP={model},syVs=7.9.1"},
    )


class TestPolling(unittest.TestCase):
    def test_disk_failure_preserves_other_readings(self):
        transport = MagicMock()
        outcomes = {ENVSTAT_COMMAND: ENVSTAT, SMART_COMMAND: SMART}

        def run_command(_, command):
            if command == DF_COMMAND:
                raise TimeCapsuleConnectionError("Disk offline")
            return outcomes[command]

        with (
            patch(
                "custom_components.time_capsule.client._connect",
                return_value=(transport, FINGERPRINT),
            ),
            patch(
                "custom_components.time_capsule.client._run_command",
                side_effect=run_command,
            ),
        ):
            result = fetch_time_capsule_data(**CONNECTION)

        self.assertEqual(set(result.errors), {"disk"})
        self.assertEqual(result.successful_checks, {"environment", "smart"})
        self.assertEqual(result.smart.status, "Passed")
        self.assertEqual(len(result.envstat), 1)
        transport.close.assert_called_once()

    def test_changed_ssh_key_is_rejected_before_password_is_sent(self):
        from custom_components.time_capsule.client import _connect

        with (
            patch("custom_components.time_capsule.client.socket.create_connection"),
            patch(
                "custom_components.time_capsule.client.paramiko.Transport"
            ) as transport_class,
        ):
            transport = transport_class.return_value
            transport.get_security_options.return_value.key_types = ()
            transport.get_remote_server_key.return_value.asbytes.return_value = (
                b"wrong key"
            )
            with self.assertRaises(TimeCapsuleIdentityError):
                _connect(**CONNECTION, fingerprint=FINGERPRINT)
            transport.auth_password.assert_not_called()
            transport.close.assert_called_once()


class TestHomeAssistant(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / "custom_components").symlink_to(
            Path(__file__).resolve().parents[1] / "custom_components"
        )
        self.hass = HomeAssistant(directory.name)
        loader.async_setup(self.hass)
        self.hass.config.skip_pip = True
        await async_from_config_dict({"homeassistant": {}}, self.hass)
        self.addAsyncCleanup(self.hass.async_stop, force=True)

    async def async_add_legacy_entry(self):
        entry = ConfigEntry(
            domain=DOMAIN,
            title="Time Capsule",
            data=CONNECTION,
            options={},
            source="user",
            version=1,
            minor_version=1,
            unique_id=CONNECTION["host"],
            discovery_keys={},
            subentries_data=None,
        )
        await self.hass.config_entries.async_add(entry)
        await self.hass.async_block_till_done()
        self.assertEqual(entry.state, ConfigEntryState.LOADED)
        return entry

    def entity_id(self, platform, key, suffix):
        value = er.async_get(self.hass).async_get_entity_id(
            platform, DOMAIN, f"{DOMAIN}_{key}_{suffix}"
        )
        self.assertIsNotNone(value)
        return value

    async def test_legacy_entity_ids_survive_reconfigure(self):
        with patch(
            "custom_components.time_capsule.fetch_time_capsule_data",
            return_value=poll_result(),
        ):
            entry = await self.async_add_legacy_entry()
            self.assertEqual(entry.version, 2)
            key = CONNECTION["host"]
            self.assertEqual(entry.data[CONF_ENTITY_KEY], key)
            old_id = self.entity_id("sensor", key, "smart_status")

            flow = await self.hass.config_entries.flow.async_init(
                DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
            )
            self.assertEqual(flow["step_id"], "reconfigure")
            new_address = "192.0.2.20"
            with patch(
                "custom_components.time_capsule.config_flow.fetch_time_capsule_data",
                return_value=poll_result(),
            ) as validate:
                result = await self.hass.config_entries.flow.async_configure(
                    flow["flow_id"], {**CONNECTION, "host": new_address}
                )
                self.assertEqual(validate.call_args.args[-1], FINGERPRINT)
            self.assertEqual(result["reason"], "reconfigure_successful")
            await self.hass.async_block_till_done()
            self.assertEqual(entry.data["host"], new_address)
            self.assertEqual(self.entity_id("sensor", key, "smart_status"), old_id)
            self.assertEqual(len(self.hass.config_entries.async_entries(DOMAIN)), 1)

    async def test_offline_then_partial_then_complete_poll(self):
        with patch(
            "custom_components.time_capsule.fetch_time_capsule_data",
            side_effect=[
                TimeCapsuleConnectionError("offline"),
                poll_result(no_disk=True),
                poll_result(),
                TimeCapsuleConnectionError("offline"),
            ],
        ):
            entry = await self.async_add_legacy_entry()
            key = CONNECTION["host"]
            connected = self.entity_id("binary_sensor", key, "ssh_connected")
            last = self.entity_id("sensor", key, "last_reading")
            disk = self.entity_id("sensor", key, "disk_free")
            self.assertEqual(self.hass.states.get(connected).state, "off")

            await entry.runtime_data.async_refresh()
            await self.hass.async_block_till_done()
            self.assertEqual(self.hass.states.get(connected).state, "on")
            self.assertEqual(
                self.hass.states.get(last).attributes["failed_checks"], ["disk"]
            )
            self.assertEqual(self.hass.states.get(disk).state, "unavailable")
            smart = self.entity_id("sensor", key, "smart_197")
            self.assertEqual(self.hass.states.get(smart).state, "0")

            await entry.runtime_data.async_refresh()
            last_value = self.hass.states.get(last).state
            self.assertNotEqual(self.hass.states.get(disk).state, "unavailable")
            await entry.runtime_data.async_refresh()
            self.assertEqual(self.hass.states.get(connected).state, "off")
            self.assertEqual(self.hass.states.get(disk).state, "unavailable")
            self.assertEqual(self.hass.states.get(last).state, last_value)

    async def test_discovery_confirms_ssh_credentials_and_sets_up_one_entry(self):
        flows = self.hass.config_entries.flow
        flow = await flows.async_init(
            DOMAIN, context={"source": "zeroconf"}, data=discovery(CONNECTION["host"])
        )
        self.assertEqual(flow["step_id"], "user")
        host_field = next(key for key in flow["data_schema"].schema if key == "host")
        self.assertEqual(
            host_field.description["suggested_value"],
            CONNECTION["host"],
        )

        with (
            patch(
                "custom_components.time_capsule.fetch_time_capsule_data",
                return_value=poll_result(),
            ),
            patch(
                "custom_components.time_capsule.config_flow.fetch_time_capsule_data",
                return_value=poll_result(),
            ),
        ):
            result = await flows.async_configure(flow["flow_id"], CONNECTION)
            await self.hass.async_block_till_done()
        entry = result["result"]
        self.assertEqual(entry.state, ConfigEntryState.LOADED)
        self.assertEqual(entry.data[CONF_AIRPORT_MAC], "02:00:00:00:00:01")
        self.assertEqual(entry.unique_id, FINGERPRINT)
        self.assertEqual(len(self.hass.config_entries.async_entries(DOMAIN)), 1)

    async def test_last_reading_is_restored_when_reloaded_offline(self):
        with patch(
            "custom_components.time_capsule.fetch_time_capsule_data",
            return_value=poll_result(),
        ):
            entry = await self.async_add_legacy_entry()
        last = self.entity_id("sensor", CONNECTION["host"], "last_reading")
        last_value = self.hass.states.get(last).state

        with patch(
            "custom_components.time_capsule.fetch_time_capsule_data",
            side_effect=TimeCapsuleConnectionError("offline"),
        ):
            await self.hass.config_entries.async_reload(entry.entry_id)
            await self.hass.async_block_till_done()

        self.assertEqual(self.hass.states.get(last).state, last_value)
        self.assertEqual(
            self.hass.states.get(last).attributes["failed_checks"],
            ["environment", "smart", "disk"],
        )

    async def test_discovery_filters_models_and_updates_only_the_verified_device(self):
        flows = self.hass.config_entries.flow
        with patch(
            "custom_components.time_capsule.fetch_time_capsule_data",
            return_value=poll_result(),
        ):
            wrong = await flows.async_init(
                DOMAIN,
                context={"source": "zeroconf"},
                data=discovery("192.0.2.10", "120"),
            )
            self.assertEqual(wrong["reason"], "not_time_capsule")
            entry = await self.async_add_legacy_entry()
            with patch(
                "custom_components.time_capsule.config_flow.fetch_time_capsule_data",
                return_value=poll_result(),
            ) as validate:
                found = await flows.async_init(
                    DOMAIN, context={"source": "zeroconf"}, data=discovery("192.0.2.10")
                )
                self.assertEqual(found["reason"], "already_configured")
                self.assertIn(CONF_AIRPORT_MAC, entry.data)
                moved = await flows.async_init(
                    DOMAIN, context={"source": "zeroconf"}, data=discovery("192.0.2.22")
                )
                self.assertEqual(moved["reason"], "already_configured")
                self.assertEqual(
                    validate.call_args.args[-1], entry.data[CONF_SSH_FINGERPRINT]
                )
                self.assertEqual(entry.data["host"], "192.0.2.22")
            with patch(
                "custom_components.time_capsule.config_flow.fetch_time_capsule_data",
                side_effect=TimeCapsuleIdentityError("changed"),
            ):
                rejected = await flows.async_init(
                    DOMAIN, context={"source": "zeroconf"}, data=discovery("192.0.2.23")
                )
            self.assertEqual(rejected["reason"], "cannot_verify_discovery")
            self.assertEqual(entry.data["host"], "192.0.2.22")
