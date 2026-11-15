# Apple Time Capsule

Time Capsule Sensors is a custom Home Assistant integration that monitors an
Apple AirPort Time Capsule over your local network. It uses SSH to read the
device's temperatures, fan speed, disk space, and drive health. Setup is
entirely in the Home Assistant UI, and readings refresh every 60 seconds.

## What you can monitor

| On the Home Assistant device page | What it shows |
| --- | --- |
| **Sensors** | Available internal and external temperature readings, fan speed (RPM), and the internal drive's total, used, and free space. Disk sizes default to TB with one decimal place. **Disk Used Percentage** and **Disk Free Percentage** are separate sensors. |
| **Sensors → SMART Status** | A drive health summary: **Passed**, **Failed**, **Disabled**, or **Not Supported**. If a critical SMART attribute reaches or falls below its threshold, the status is **Failed** and the sensor lists which attributes failed. |
| **Diagnostics** | Individual SMART readings reported by the drive, such as disk temperature, power-on hours, pending sectors, and reallocated sectors. Each sensor shows the raw reading and includes the normalized value, threshold, and whether the attribute is critical. Unrecognized attributes include their numeric ID in the name. |

In Home Assistant, you can create an alert when **Disk Free Percentage** gets low
or **SMART Status** changes to **Failed**, and chart temperature and fan speed
over time. These readings describe the Time Capsule and its drive; they don't
tell you when a Mac last completed a Time Machine backup.

## Before you install

- **Enable SSH on the Time Capsule.** Stock firmware doesn't allow SSH logins.
  [TimeCapsuleSMB](https://github.com/jamesyc/TimeCapsuleSMB) can enable SSH when
  you add the device in its macOS app or run `tcapsule configure` in the CLI.
  The integration only needs SSH access; it doesn't require a Samba installation.
- **Have the device password handy.** Use the Time Capsule's base station admin
  password, the same one you enter in TimeCapsuleSMB.
- **Choose an address Home Assistant can reach.** Use a hostname that resolves
  from Home Assistant or an IP address. If you use an IP address, reserve it in
  your router's DHCP settings so it stays the same.

AirPort Extreme compatibility is unverified. Setup currently expects the
internal drive and filesystem commands used by the Time Capsule.

## Install

### HACS (recommended)

[![Open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jtenniswood&repository=hass-time-capsule&category=integration)

You can also open **HACS → ⋮ → Custom repositories**, add
`https://github.com/jtenniswood/hass-time-capsule` with the type **Integration**,
then find **Time Capsule Sensors** and download it. Restart Home Assistant.

### Manual

Download the source archive from the [latest release](https://github.com/jtenniswood/hass-time-capsule/releases/latest).
Copy the whole `custom_components/time_capsule` folder into Home Assistant's
`config/custom_components/` directory, then restart Home Assistant.

## Connect your Time Capsule

1. Go to **Settings → Devices & services → Add integration** and search for
   **Time Capsule Sensors**.
2. Enter the Time Capsule's hostname or IP address, SSH username (default
   `root`), SSH port (default `22`), and base station admin password.
3. Submit the form. Home Assistant checks the SSH login and runs the sensor
   commands before it saves the connection.

Home Assistant uses the base station name from AirPort Utility when it can
read it. If you rename the base station in AirPort Utility, reload the
integration entry to pick up the new name. To edit the connection details,
open the integration entry and select **Configure**.

If setup reports a connection error, check the address, port, and whether
SSH is enabled and reachable from Home Assistant. If it reports an
authentication error, check the SSH username and base station admin password.
If existing sensors become unavailable, check **Settings → System → Logs**
for polling errors.

## How it works

Each poll opens one SSH connection and runs `envstat` for temperature and fan
speed, `atactl wd0 smart status` for drive health, and `df /dev/dk2` for disk
usage. On load, it also tries `acp -q syNm` to read the base station name.

The integration handles the older SSH algorithms the Time Capsule requires
(`diffie-hellman-group14-sha1` and `ssh-rsa`). No manual SSH client configuration
is needed in Home Assistant.

[Release history](https://github.com/jtenniswood/hass-time-capsule/releases) · [License](LICENSE)
