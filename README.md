# Elmo Modbus for Home Assistant

[![HACS Custom Integration](https://img.shields.io/badge/HACS-Custom-blue.svg)](https://hacs.xyz/)
[![Modbus](https://img.shields.io/badge/Protocol-Modbus%20TCP-0A5FFF.svg)](https://www.modbus.org/)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2023.8%2B-41BDF5.svg)](https://www.home-assistant.io/)

A polished Home Assistant integration for supervising and controlling Elmo alarm control panels over Modbus TCP. It exposes a feature-rich alarm control panel entity, optional binary sensors for inputs, diagnostic entities, Modbus output switches, and helper sensors that make it easy to build dashboards and automations tailored to your installation.

**IMPORTANT! THIS INTEGRATION REQUIRES MODBUS MODULE INSTALLED IN CONTROL PANEL OR MODBUS GATEWAY**

---

## Table of contents

1. [Features](#features)
2. [Requirements](#requirements)
3. [Installation](#installation)
   - [HACS (recommended)](#hacs-recommended)
   - [Manual installation](#manual-installation)
4. [Configuration](#configuration)
   - [Initial setup](#initial-setup)
   - [Managing panels and sectors](#managing-panels-and-sectors)
   - [Mapping inputs to binary sensors](#mapping-inputs-to-binary-sensors)
   - [Exposing Modbus outputs as switches](#exposing-modbus-outputs-as-switches)
   - [Providing user codes](#providing-user-codes)
5. [Entities created](#entities-created)
6. [Troubleshooting & tips](#troubleshooting--tips)
7. [Contributing](#contributing)

---

## Features

- **Native config flow** – onboard the integration directly from Home Assistant’s UI, including host/port, sector count, and scan interval settings.【F:custom_components/elmo-modbus/config_flow.py†L64-L108】
- **Flexible panel definitions** – create multiple virtual panels with custom names and sector assignments for away/home/night modes, letting you mirror the arming scenarios available on your Elmo hardware.【F:custom_components/elmo-modbus/alarm_control_panel.py†L47-L122】
- **Alarm control panel entity** – arm, disarm, and monitor the panel state in real time. Optional code validation prevents unauthorised actions from automations or dashboard widgets.【F:custom_components/elmo-modbus/alarm_control_panel.py†L124-L217】
- **Rich diagnostics** – leverage built-in binary sensors covering power, tamper, communication, and sector diagnostics alongside optional per-input binary sensors mapped to Modbus discrete inputs.【F:custom_components/elmo-modbus/binary_sensor.py†L1-L137】【F:custom_components/elmo-modbus/binary_sensor.py†L171-L224】
- **Environmental insights** – monitor panel temperature with a dedicated sensor sourced from Modbus holding registers.【F:custom_components/elmo-modbus/sensor.py†L1-L68】
- **Output control** – toggle Modbus-controlled relays or programmable outputs through Home Assistant switch entities, complete with custom naming support.【F:custom_components/elmo-modbus/switch.py†L1-L120】
- **Responsive updates** – low-latency polling (default 1s) keeps entity state in sync while still letting you tune the scan interval to suit your network.【F:custom_components/elmo-modbus/const.py†L5-L13】

## Requirements

- A Home Assistant installation version **2023.8.0 or newer** (per HACS manifest).【F:hacs.json†L1-L7】
- An Elmo alarm panel with a Modbus TCP interface reachable from your Home Assistant network.
- Firewall/network rules allowing outbound TCP connections from Home Assistant to the Modbus host (default port `502`).

## Installation

1### HACS (recommended)

1. Add this repository (`https://github.com/ha-elmo-modbus/ha-elmo-modbus`) as a **custom repository** in HACS (Category: *Integration*).
2. Install **Elmo Modbus** from the *Integrations* tab.
3. Restart Home Assistant when prompted to load the new integration module.

### Manual installation

1. Download the latest release archive from GitHub.
2. Copy the `custom_components/elmo-modbus` folder into your Home Assistant configuration directory.
3. Restart Home Assistant to register the integration.

## Configuration

### Initial setup

1. Navigate to **Settings → Devices & Services → + Add Integration** and search for **Elmo Modbus**.
2. Provide a friendly name, the Modbus TCP host/IP, port, desired scan interval (in seconds), and the number of sectors exposed by your panel.【F:custom_components/elmo-modbus/config_flow.py†L88-L108】
3. Submit to create the config entry. The integration will immediately connect and begin polling the panel status.

### Managing panels and sectors

- Use the integration’s **Options** menu to define one or more virtual panels, each with its own sector assignments for Away, Home, and Night modes. The integration automatically maps the configured sectors to Modbus coils when issuing arm/disarm commands.【F:custom_components/elmo-modbus/alarm_control_panel.py†L47-L153】
- Panels can optionally limit which sectors they manage when disarming, letting you scope control to specific partitions.【F:custom_components/elmo-modbus/alarm_control_panel.py†L155-L187】

### Mapping inputs to binary sensors

- In the **Options → Inputs** step, list the Modbus input numbers you want to expose. Each input becomes a binary sensor entity with automatic or custom naming and per-entity unique IDs, making them easy to reference in automations.【F:custom_components/elmo-modbus/binary_sensor.py†L139-L236】
- Custom names (Options → Input names) let you label detectors or zones directly from the UI – the integration handles slug creation and entity ID updates for you.【F:custom_components/elmo-modbus/binary_sensor.py†L205-L236】

### Exposing Modbus outputs as switches

- In **Options → Outputs**, enter the Modbus output numbers that should surface as switch entities. These switches use the same coordinator as the binary sensors for efficient polling.【F:custom_components/elmo-modbus/switch.py†L25-L120】
- Assign human-friendly names (Options → Output names) and the integration will keep entity IDs aligned with your naming to avoid breaking existing dashboards and automations.【F:custom_components/elmo-modbus/switch.py†L73-L109】

### Providing user codes

- If you require a PIN to arm/disarm, add one or more valid codes in **Options → User codes**. Only automations or users providing one of the configured codes can change the alarm state, providing an extra safety layer.【F:custom_components/elmo-modbus/alarm_control_panel.py†L91-L122】【F:custom_components/elmo-modbus/alarm_control_panel.py†L189-L217】

## Entities created

| Platform | Description | Notes |
|----------|-------------|-------|
| `alarm_control_panel` | Controls one or more virtual panels with Away/Home/Night support and optional code validation. | Commands are translated into Modbus coil writes targeting the configured sectors.【F:custom_components/elmo-modbus/alarm_control_panel.py†L187-L244】 |
| `binary_sensor` | Diagnostics covering power, tamper, communication, sector state, plus optional per-input sensors. | Input sensors map to Modbus discrete inputs starting at address `0x1001` (`4097`).【F:custom_components/elmo-modbus/binary_sensor.py†L39-L132】【F:custom_components/elmo-modbus/binary_sensor.py†L171-L201】 |
| `sensor` | Reports the panel’s internal temperature in °C. | Invalid values from the Modbus register are filtered out before exposing the state.【F:custom_components/elmo-modbus/sensor.py†L40-L68】 |
| `switch` | Lets you toggle Modbus outputs (e.g., relays, indicators) directly from Home Assistant. | Writes are sent via `write_coils`, with connection retries and coordinator refreshes to keep state accurate.【F:custom_components/elmo-modbus/switch.py†L121-L206】 |

## Troubleshooting & tips

- **Connection errors**: Ensure the Modbus endpoint is reachable and only one client is connected at a time. The integration retries connections on demand but persistent failures will surface in the Home Assistant logs as `ConnectionException` errors.【F:custom_components/elmo-modbus/alarm_control_panel.py†L205-L217】【F:custom_components/elmo-modbus/switch.py†L155-L206】
- **Polling impact**: The default 1-second scan interval keeps the alarm state responsive. Increase the interval in the options flow if your network or panel struggles with rapid polling.【F:custom_components/elmo-modbus/const.py†L5-L13】
- **Entity names/IDs**: Updating names via the options flow automatically refreshes entity IDs when safe to do so, helping you avoid stale references in dashboards.【F:custom_components/elmo-modbus/binary_sensor.py†L209-L236】【F:custom_components/elmo-modbus/switch.py†L85-L109】

## Contributing

Issues and pull requests are welcome! Please open a GitHub issue for bugs or feature requests, and feel free to submit PRs that align with Home Assistant integration best practices. Development helpers like `pymodbus` are declared in the manifest so your environment stays reproducible.【F:custom_components/elmo-modbus/manifest.json†L1-L12】