# Panasonic MirAI.e Integration for Home Assistant

This integration allows you to control your Panasonic MirAI.e air conditioners through Home Assistant using the official MirAI.e API and MQTT protocol.

## Features

- Control multiple Panasonic MirAI.e air conditioners
- Set target temperature
- Change operation modes (Auto, Cool, Heat, Dry, Fan Only)
- Adjust fan speed (Auto, Low, Medium, High, Quiet)
- Control swing mode (Off, Vertical, Horizontal, Both)
- Monitor current room temperature
- View and control additional features:
  - NanoeTM X (On/Off)
  - Powerful mode (On/Off)
  - Economy mode (On/Off)
- Monitor filter status:
  - Dust level
  - Cleaning required indicator
- View device errors and warnings

## Requirements

- Home Assistant version 2024.1.0 or higher
- A Panasonic MirAI.e account with registered devices

## Installation

### HACS (Recommended)

1. Ensure that [HACS](https://hacs.xyz/) is installed.
2. Search for "Panasonic MirAI.e" in the HACS integrations tab.
3. Click Install.
4. Restart Home Assistant.

### Manual Installation

1. Download the latest release from the [GitHub repository](https://github.com/chrissmartin/hass-panasonic-miraie).
2. Unzip the release and copy the `custom_components/panasonic_miraie` directory to your Home Assistant's `custom_components` directory.
3. Restart Home Assistant.

## Configuration

1. In the Home Assistant UI, go to "Configuration" -> "Integrations".
2. Click the "+" button to add a new integration.
3. Search for "Panasonic MirAI.e" and select it.
4. Enter your MirAI.e account credentials (user ID/email and password).
5. The integration will automatically discover and add your MirAI.e devices.

## Usage

After configuration, your Panasonic MirAI.e devices will appear as climate entities in Home Assistant. You can control them through the Home Assistant UI, Lovelace cards, or include them in automations and scripts.

### Climate Entity Attributes

Each MirAI.e device will have the following attributes:

- `current_temperature`: The current room temperature
- `target_temperature`: The set target temperature
- `hvac_mode`: The current operation mode (off, auto, cool, heat, dry, fan_only)
- `fan_mode`: The current fan speed (auto, low, medium, high, quiet)
- `swing_mode`: The current swing setting (off, vertical, horizontal, both)
- `nanoe_x`: Status of NanoeTM X feature (on/off)
- `powerful_mode`: Status of Powerful mode (on/off)
- `economy_mode`: Status of Economy mode (on/off)
- `filter_dust_level`: Current dust level in the filter
- `filter_cleaning_required`: Indicator if filter cleaning is required
- `errors`: Any current device errors
- `warnings`: Any current device warnings

## Troubleshooting

- If you encounter connection issues, ensure your Home Assistant instance has a stable internet connection.
- Check the Home Assistant logs for any error messages related to the Panasonic MirAI.e integration.
- If you experience authentication problems, try to log out and log in again in the MirAI.e mobile app, then reconfigure the integration in Home Assistant.

## Contributing

Contributions to improve the integration are welcome! Please feel free to submit pull requests or open issues for any bugs or feature requests on the [GitHub repository](https://github.com/chrissmartin/hass-panasonic-miraie).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This integration is not officially affiliated with or endorsed by Panasonic. Use at your own risk.
