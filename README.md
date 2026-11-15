# Apple Time Capsule

Time Capsule Sensors is a custom Home Assistant integration that monitors an
Apple AirPort Time Capsule over your local network. It uses SSH to read the
device's temperatures, fan speed, disk space, and drive health. Setup is
entirely in the Home Assistant UI, and readings refresh every 60 seconds.

## What you can monitor

| On the Home Assistant device page | What it shows |
| --- | --- |
| **Sensors** | Available internal and external temperature readings, fan speed (RPM), and the internal drive's total, used, and free space. Disk sizes default to TB with one decimal place. **Disk Used Percentage** and **Disk Free Percentage** are separate sensors. |
| **Sensors → SMART Status** | A drive health summary: **Passed**, **Failed**, **Unknown**, **Disabled**, or **Not Supported**. A drive-reported failure or a critical attribute at or below its threshold sets **Failed**. An incomplete report shows **Unknown**. |
| **Diagnostics → SSH Connected and Last Successful Reading** | Whether Home Assistant can connect and when each sensor check last succeeded. |
| **Diagnostics** | Individual SMART readings reported by the drive, such as disk temperature, power-on hours, pending sectors, and reallocated sectors. Each sensor shows the raw reading and includes the normalized value, threshold, and whether the attribute is critical. Unrecognized attributes include their numeric ID in the name. |

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

AirPort Extreme compatibility is unverified.

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

1. Go to **Settings → Devices & services**. If your fifth-generation Time
   Capsule appears under **Discovered** via Bonjour, select **Configure**.
   For manual setup, choose **Add integration → Time Capsule Sensors**.
2. Enter the Time Capsule's hostname or IP address, SSH username (default
   `root`), SSH port (default `22`), and base station admin password.
3. Submit the form. Home Assistant checks the SSH login and runs the sensor
   commands before it saves the connection.

Home Assistant uses the base station name from AirPort Utility when it can
read it. If you rename the base station in AirPort Utility, reload the
integration entry to pick up the new name. To edit the connection details,
open the integration entry menu and select **Reconfigure**. Existing sensors
keep their IDs and history when the address changes. Home Assistant remembers
the SSH key on the first successful poll after upgrading. An announcement from
a known Time Capsule can update its address after the SSH key is verified.

If setup reports a connection error, check the address, port, and whether
SSH is enabled and reachable from Home Assistant. If it reports an
authentication error, check the SSH username and base station admin password.
If existing sensors become unavailable, check **SSH Connected** and
**Last Successful Reading** on the device page.

## Alerts and backup monitoring

- **Connection loss** Use **SSH Connected** to alert after several minutes
  offline. Use **Last Successful Reading** to catch a poll that connects over
  SSH but returns no usable measurements.
- **Disk trouble** Alert when SMART becomes **Failed**, stays **Unknown**,
  pending sectors appear, or reallocated sectors increase. The two sector
  counters depend on what your disk reports.
- **Disk space** Alert when free space stays below a threshold that suits your
  backup size. Confirm the disk sensor's unit in Home Assistant when setting
  the threshold.
- **Cooling** Use the temperature and fan graphs to establish a baseline under
  a normal backup load. Set a sustained high-temperature alert based on your
  drive's limits and typical readings.

The [monitoring package](examples/monitoring.yaml) provides example Home
Assistant notifications for connection, SMART, disk space, and stalled readings.
Copy it into your [Home Assistant packages folder](https://www.home-assistant.io/docs/configuration/packages/)
and replace its sample entity IDs and thresholds. Use a copy with distinct
automation IDs for each additional Time Capsule.

You can also monitor **time since the last completed Time Machine backup** on
each Mac that uses the Time Capsule as a destination:

1. Install the [Time Machine package](examples/time_machine_backup.yaml) in
   Home Assistant. Add a long random `time_machine_mac_webhook` value to
   `secrets.yaml` and reload or restart Home Assistant. Use a separate secret
   and distinct sensor, automation, and entity IDs for each Mac and destination.
2. On the Mac, use `tmutil destinationinfo` to find the mounted backup destination.
   Run the [reporting script](examples/report-time-machine-backup.sh) from
   Terminal with Full Disk Access. Substitute the actual mounted backup **volume**
   and your Home Assistant address. If macOS requires root for `tmutil`, invoke
   the script with `sudo` from that Terminal.
   ```sh
   ./report-time-machine-backup.sh "/Volumes/Your Backup Volume" \
       "https://home-assistant.example/api/webhook/YOUR_WEBHOOK_ID"
   ```
3. Check that **Mac Last Time Capsule Backup** matches the time shown by Time
   Machine. Run the reporter when the destination is mounted. The backup age
   updates in Home Assistant between reports, and the sample alert fires
   after 48 hours. Each successful report sends only a timestamp to the
   local webhook.

## Finding other network devices

Time Capsule discovery finds supported AirPort base stations that advertise
via Bonjour. For a wider inventory use your router's device integration or
[Home Assistant's Nmap Tracker](https://www.home-assistant.io/integrations/nmap_tracker/).
A scan shows the devices that respond from Home Assistant's network and does
not tell you which Wi-Fi access point each device is using. AirPort Utility
can show the status of each Time Capsule.

## How it works

Each poll opens one SSH connection and runs `envstat` for temperature and fan
speed, `atactl wd0 smart status` for drive health, and `df /dev/dk2` for disk
usage. The checks can fail independently. On the first successful SSH
connection after loading, it also tries `acp -q syNm` to read the base station
name.

The integration handles the older SSH algorithms the Time Capsule requires
(`diffie-hellman-group14-sha1` and `ssh-rsa`). No manual SSH client configuration
is needed in Home Assistant.

[Release history](https://github.com/jtenniswood/hass-time-capsule/releases) · [License](LICENSE)
