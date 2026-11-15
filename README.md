# Apple Time Capsule

<img src="custom_components/time_capsule/brand/icon.png" alt="Apple Time Capsule integration icon" width="128" height="128">

Time Capsule Sensors is a custom Home Assistant integration that monitors an
Apple AirPort Time Capsule over your local network. It uses SSH to read the
device's temperature, fan speed, disk space, and drive health. Setup is
entirely in the Home Assistant UI, and readings refresh every 60 seconds.

## What you can monitor

| On the Home Assistant device page | What it shows |
| --- | --- |
| **Sensors** | The internal drive's total, used, and free space. Disk sizes default to TB with one decimal place. **Disk Used Percentage** and **Disk Free Percentage** are separate sensors. |
| **Sensors → SMART Status** | A drive health summary: **Passed**, **Failed**, **Unknown**, **Disabled**, or **Not Supported**. A drive-reported failure or a critical attribute at or below its threshold sets **Failed**. An incomplete report shows **Unknown**. |
| **Diagnostics → Last Successful Reading** | When the most recent hardware reading arrived, with timestamps for each check. |
| **Diagnostics → Backup Volume Mounted** | Whether the internal backup filesystem is mounted. |
| **Diagnostics → SMB Port Open and SMB Share Accessible** | Optional checks from Home Assistant for TCP port 445 and read-only access to the configured share. |
| **Diagnostics → Fan Speed** | Fan speed in RPM. |
| **Diagnostics → Temperature** | A single reading, using drive temperature when available, then airflow temperature or a Time Capsule temperature reading. |
| **Diagnostics → Drive health readings** | Reallocated sectors, pending sectors, offline uncorrectable sectors, reported uncorrectable errors, spin retries, Ultra DMA CRC errors, power cycles, and power-on days. Readings appear when the drive reports them. |

On upgrade, Home Assistant removes retired sensors from the device. If an
alert used **SSH Connected**, select **Backup Volume Mounted** in the alert
blueprint. If a temperature alert used a retired sensor, select
**Temperature** and check that the limit suits the new reading.

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

[![Open Devices & services in Home Assistant](https://my.home-assistant.io/badges/integrations.svg)](https://my.home-assistant.io/redirect/integrations/)

1. After restarting Home Assistant, open **Settings → Devices & services →
   Integrations**. If your fifth-generation Time Capsule appears under
   **Discovered** via Bonjour, select **Configure**. Otherwise, choose
   **Add integration → Time Capsule Sensors → Enter address manually**.
2. Enter the Time Capsule's hostname or IP address, SSH username (default
   `root`), SSH port (default `22`), and base station admin password.
   Bonjour discovery fills in the Time Capsule's IP address.
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
If sensors become unavailable, check **Last Successful Reading** on the
device page.

## Check the backup volume and share

**Backup Volume Mounted** checks the internal data volume, including when disk
capacity is temporarily unreadable. If SSH is unavailable, Home Assistant
shows the mount check as unavailable.

To monitor a TimeCapsuleSMB share, open the integration's **Configure** options
and enable **Monitor the SMB service**.

- **SMB Port Open** checks whether Home Assistant can open TCP port 445.
- **SMB Share Accessible** is added when you enter the share name, SMB username,
  and SMB password. It uses SMB 2 or 3 and opens the share for read-only access.
  Enter the share name by itself, such as `Data`, and use the account you
  configured for SMB. To keep its password when editing the same share and
  username, leave the password field blank.

The SMB checks run independently of regular SSH outages. A successful check
shows that Home Assistant can open the share. Each Mac's backup reporter
shows whether that Mac completed a backup to its configured destination.

## Set up alerts

[![Import the Time Capsule alert blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fjtenniswood%2Fhass-time-capsule%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Ftime-capsule%2Fmonitoring.yaml)

1. In **Settings → Devices & services → Helpers**, create a **Text** helper
   with a maximum length of **255**. Give each alert automation its own helper
   so it can remember active alerts and sector counts across restarts.
2. Import the [Time Capsule alert blueprint](blueprints/automation/time-capsule/monitoring.yaml).
   Create an automation from it, select the helper, and choose the sensor
   inputs you want to use. Select **Backup Volume Mounted** or the optional SMB
   sensors under **Connection and mount sensors**.
3. Keep the default Home Assistant notification or set your own notification
   action. Use `{{ message }}` in the message field to include the fault or
   recovery details.

SMART failure and rising sector counts are checked each minute. Connection
outages, high temperatures, and low space use the configured delays. If you
enable temperature alerts, set the limit in the sensor's displayed unit and
use the drive's limits and your normal backup readings as a guide. The
[original YAML example](examples/monitoring.yaml) is available for existing
setups. Disable any overlapping alerts when switching to the blueprint.

## Monitor completed Time Machine backups

Set up one webhook and reporter per Mac and backup destination.

1. Copy the [Time Machine package](examples/time_machine_backup.yaml) into your
   [Home Assistant packages folder](https://www.home-assistant.io/docs/configuration/packages/).
   Add a long random `time_machine_mac_webhook` value to `secrets.yaml` and
   restart Home Assistant. For each additional Mac or destination, copy the
   package and use distinct values for the webhook secret, sensor names,
   unique IDs, and example automation ID and name. Replace the last-backup
   and backup-age entity IDs wherever the new package refers to them.
2. On the Mac, run `tmutil destinationinfo` to identify the intended Time
   Capsule destination, then check its mounted volume in Finder or with
   `mount`. Run the [reporter](examples/report-time-machine-backup.sh) in
   Terminal with Full Disk Access. Use the actual mount path and your Home
   Assistant address. If `tmutil` requires root, run it with `sudo` from the
   same Terminal.

   ```sh
   bash report-time-machine-backup.sh "/Volumes/Your Backup Volume" \
       "https://home-assistant.example/api/webhook/YOUR_WEBHOOK_ID"
   ```

3. After a successful backup, compare **Mac Last Time Capsule Backup** with
   Time Machine. Run the same reporter when the volume is unmounted to confirm
   that **Mac Time Capsule Reporter Status** changes to
   `destination_unavailable` and the last completed backup stays recorded.
   A mounted volume that `tmutil` can't read reports `read_error`.
4. To get alerts, select the Mac's backup age, last report, and reporter status
   in a blueprint automation. Disable the package's example overdue automation
   if the blueprint also monitors backup age. Set the report timeout based on
   how often you run the reporter and how long the Mac normally sleeps. The reporter
   sends its status and, when readable, the last completed backup timestamp
   to a local-only webhook.

## Share diagnostics

Open the Time Capsule integration's entry menu and select **Download
diagnostics** to export the latest check results and decoded measurements.
The export omits connection and account details. See the
[hardware sample guide](tests/fixtures/README.md) to help verify an additional
model, firmware version, or replacement drive.

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
usage. When disk usage is unreadable, it checks the mount table separately.
The checks can fail independently. On the first successful SSH
connection after loading, it also tries `acp -q syNm` to read the base station
name.

The integration handles the older SSH algorithms the Time Capsule requires
(`diffie-hellman-group14-sha1` and `ssh-rsa`). No manual SSH client configuration
is needed in Home Assistant.

[Release history](https://github.com/jtenniswood/hass-time-capsule/releases) · [License](LICENSE)
