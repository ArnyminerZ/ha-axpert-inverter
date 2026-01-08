# Axpert Inverter Home Assistant Integration

This custom component integrates Axpert Inverters directly into Home Assistant via USB (HID), replacing the need for external tools like `mppsolar` or MQTT bridges. It communicates directly with the inverter using the QPIGS protocol.

> [!IMPORTANT]
> This integration is not affiliated with or endorsed by Axpert.
> It is a completely independent project, backed up by the community, and based on official documentation, commands, and reverse engineering.

> [!NOTE]
> **Disclaimer:** this project has been generated mainly by AI. Even though it has been reviewed and tested by a professional programmer, I feel like it's important to disclose this fact.

## Features

- **Direct Communication**: Reads data directly from `/dev/hidrawX`, no separate MQTT broker required.
- **Real-time Sensors**:
    - Grid Voltage & Frequency
    - AC Output Voltage, Frequency, Active Power (W), Apparent Power (VA)
    - Battery Voltage, Charging Current, Capacity (%)
    - PV Input Voltage, Current, and Power
- **Energy Metering**:
    - Built-in kWh accumulation for **PV Energy** (Solar Generation) and **Load Energy** (Consumption).
    - Fully compatible with the **Home Assistant Energy Dashboard**.
- **Control**:
    - **AC Input Range Selection**: Switch between "Appliance" (Generator friendly) and "UPS" (Grid) modes directly from HA.
- **Diagnostics**:
    - Reports Inverter Firmware Version.

## Prerequisites
### Prepare the Device
Ensure your Home Assistant host has access to the inverter's USB port.
- If using Docker, map the device: `--device /dev/hidraw0:/dev/hidraw0`.
- Stop any other services using the port (e.g., `mppsolar` container).

## Installation

### Option 1: HACS (Recommended)
1.  Open **HACS** in Home Assistant.
2.  Go to **Integrations** > **Three dots (top right)** > **Custom repositories**.
3.  Add the URL of this repository and select **Integration** as the category.
4.  Click **ADD**.
5.  Find **Axpert Inverter** in the list and click **Download**.
6.  Restart Home Assistant.

### Option 2: Manual Installation
1.  Copy the `custom_components/axpert_inverter` directory into your Home Assistant's `config/custom_components/` folder.
    ```bash
    cp -r custom_components/axpert_inverter /config/custom_components/
    ```
2.  Restart Home Assistant.

## Configuration

1.  In Home Assistant, go to **Settings** > **Devices & Services**.
2.  Click **+ ADD INTEGRATION**.
3.  Search for **Axpert Inverter**.
4.  Enter the **Device Path** (default: `/dev/hidraw0`).
5.  Click **Submit**.

If connection is successful, the integration will load and entities will become available.

## Usage

### Energy Dashboard Setup
To track your solar production and home usage:
1.  Go to **Energy** section in Settings.
2.  Under **Solar Panels**, add the entity `sensor.axpert_pv_energy`.
3.  Under **Home Usage**, add the entity `sensor.axpert_load_energy`.

### Configuring AC Input (Grid vs Generator)
Use the **AC Input Range** select entity (`select.axpert_ac_input_range`) to configure the input voltage sensitivity:
-   **Appliance (Generator)**: Sets wide input range (90-280V). Use this when running on a generator to prevent rejection of dirty power.
-   **UPS (Grid)**: Sets narrow input range (170-280V). Use this for stable grid power for better protection of sensitive electronics.

## Troubleshooting

-   **Connection Failed**: Verify the device path exists and Home Assistant has read/write permissions.
-   **Entities Unavailable**: Check the logs. If the inverter is off (only battery/solar), USB communication might be down depending on the model.
