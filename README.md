# Elmo Modbus Home Assistant Integration

This repository contains a custom Home Assistant integration that creates an alarm
control panel entity backed by a Modbus-connected Elmo control panel.

## Features

- Config flow for entering the Modbus TCP host and port.
- Periodic polling of holding register `1234` to determine alarm status.
- Alarm control panel entity that exposes the panel state and raw status register.

## Installation

1. Copy the `custom_components/elmo_modbus` directory into your Home Assistant
   configuration folder.
2. Restart Home Assistant.
3. Add the **Elmo Modbus** integration from the Home Assistant integrations UI
   and provide the IP address and port of the control panel.