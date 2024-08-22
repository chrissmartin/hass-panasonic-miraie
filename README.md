# Panasonic MirAI.e Integration for Home Assistant

This integration allows you to control your Panasonic MirAI.e air conditioners through Home Assistant.

## Features

- Control multiple Panasonic MirAI.e air conditioners
- Set temperature
- Change operation modes
- Adjust fan speed
- Monitor current temperature and humidity (if supported by your AC model)

## Installation

### HACS (Recommended)

1. Ensure that [HACS](https://hacs.xyz/) is installed.
2. Search for "Panasonic MirAI.e" in the HACS integrations tab.
3. Install the integration.
4. Restart Home Assistant.

### Manual Installation

1. Copy the `custom_components/panasonic_miraie` directory to your Home Assistant's `custom_components` directory.
2. Restart Home Assistant.

## Configuration

1. In the Home Assistant UI, go to "Configuration" -> "Integrations".
2. Click the "+" button to add a new integration.
3. Search for "Panasonic MirAI.e" and select it.
4. Follow the configuration steps to enter your MirAI.e account credentials.

## Usage

After configuration, your Panasonic MirAI.e devices will appear as climate entities in Home Assistant. You can control them through the Home Assistant UI or include them in automations and scripts.

## Contributing

Contributions to improve the integration are welcome! Please feel free to submit pull requests or open issues for any bugs or feature requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
