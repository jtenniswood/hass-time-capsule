# Apple Time Capsule

A Home Assistant integration for modded Apple Time Capsules. It polls the
device once a minute and reports:

- Temperature sensors: internal, and external 1-3.
- Fan speed (RPM).
- A sensor for every SMART attribute the drive reports (raw value, with the
  normalized value/threshold/criticality as attributes) -- reallocated
  sectors, power-on hours, pending sectors, temperature, and so on.
- An overall SMART Status sensor (`Passed` / `Failed` / `Disabled` /
  `Not Supported` / `Unknown`).
- Disk usage for the internal drive: total, used, free, percent used, and
  percent free.
- **SSH Connected** and **Last Successful Reading**. The timestamp has an
  individual last-success time for temperature and fan, SMART, and disk usage.
  It also lists which checks are failing.

On the Time Capsule device page, individual SMART readings and the new
connection and freshness sensors appear under **Diagnostics**. The **Sensors**
section shows Time Capsule temperatures, fan speed, disk usage, and overall
SMART Status.

It may also work with an AirPort Extreme, since it shares the same internal
tooling, but that hasn't been tested -- if you try it, let me know via an
issue.

## Prerequisites

### 1. Enable SSH on the Time Capsule

Stock Time Capsule firmware doesn't allow SSH logins. Use
[TimeCapsuleSMB](https://github.com/jamesyc/TimeCapsuleSMB) first -- besides
installing modern Samba, its setup step enables SSH on the device for you
(it needs your Time Capsule's admin password to do that). Run its
`configure` step (or the equivalent step in its macOS GUI app) and confirm
SSH comes up before moving on.

### 2. If you'll use an IP address, make it static

The integration accepts either a hostname or an IP address for the Time
Capsule. If you use an IP, reserve it in your router (DHCP reservation,
sometimes called a "static lease" or "address reservation" -- look up your
router's admin UI for the exact term), keyed to the Time Capsule's MAC
address, so it doesn't change on you later. A hostname doesn't need this,
as long as it reliably resolves to the device.

### 3. Know your Time Capsule's password

The SSH password is your Time Capsule's own admin password -- the same one
you used with TimeCapsuleSMB above.

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mdevils&repository=hass-time-capsule&category=integration)

Or manually: HACS -> the "..." menu (top right) -> **Custom repositories**
-> add `https://github.com/mdevils/hass-time-capsule` as an **Integration**
-> find "Time Capsule Sensors" in HACS and install it.

Restart Home Assistant after installing.

### Manual

Copy `custom_components/time_capsule` into your Home Assistant `config/custom_components/` directory, then restart Home Assistant.

## Configuration

Configuration is done entirely from the UI -- there's no YAML.

1. Open **Settings → Devices & services**. A fifth-generation Time Capsule on
   the same network can appear under **Discovered** via Bonjour. Choose
   **Configure** on the discovered device. For manual setup, select
   **Add integration → Time Capsule Sensors**.
2. Enter:
   - **Host**: the Time Capsule's hostname or IP address.
   - **Username**: `root` by default.
   - **Port**: `22` by default.
   - **Password**: the Time Capsule's admin password, from the prerequisites above.
3. The integration connects and fetches real data before saving, so a wrong
   host/password shows an inline error immediately instead of failing
   silently later.

To change connection details later, open the integration's entry menu and choose
**Reconfigure**. Existing entities keep their IDs and history when the address
changes. An existing installation remembers the SSH key on its first successful
poll after upgrading. A discovered device can update its saved address when it
is seen again and its SSH key is verified.

The poll interval is fixed at 60 seconds and isn't currently exposed in the
UI.

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

The integration authenticates over SSH and runs three commands: `envstat`,
for the temperature and fan readings; `atactl wd0 smart status`, for the
SMART table; and `df /dev/dk2`, for disk usage. Each check can fail
independently. The SMART sensor shows **Failed** when the drive reports a
failure or a critical attribute reaches its threshold. It shows **Passed**
when the enabled SMART table is readable and reports no failure, and
**Unknown** when the report is incomplete.

These Time Capsules run an old NetBSD-based `sshd` that only offers a
`diffie-hellman-group14-sha1` key exchange and signs its host key with
plain `ssh-rsa` -- both long dropped as defaults by current OpenSSH and
Paramiko. The integration requests them explicitly, so no manual SSH
configuration is needed on your end.
