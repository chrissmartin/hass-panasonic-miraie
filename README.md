# Panasonic MirAIe Integration for Home Assistant

This integration allows you to control your Panasonic MirAIe air conditioners through Home Assistant using the official MirAIe API and MQTT protocol.

## Features

- Control multiple Panasonic MirAIe air conditioners
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
- A Panasonic MirAIe account with registered devices

## Installation

### Installing via HACS (Recommended)

The easiest way to install the **hass-panasonic-miraie** is through [HACS (Home Assistant Community Store)](https://hacs.xyz/).

#### **Step 1: Install HACS**

If you haven't installed HACS yet, follow the [official installation guide](https://hacs.xyz/docs/setup/download) to set it up.

#### **Step 2: Add Custom Repository**

1. Open your Home Assistant instance.
2. Navigate to **HACS** in the sidebar.
3. Click on the **Integrations** tab.
4. Click on the three-dot menu (⋮) in the top right corner.
5. Select **Custom repositories**.

   ![Custom Repositories](https://www.hacs.xyz/assets/images/screenshots/overview/menu/dark.png#only-dark)

6. In the **Add custom repository URL** field, enter:

   ```url
   https://github.com/chrissmartin/hass-panasonic-miraie
   ```

7. In the **Category** dropdown, select **Integration**.
8. Click **Add**.

#### **Step 3: Install the Integration**

1. After adding the repository, search for **Panasonic MirAIe** in HACS.
2. Click on the integration to view details.
3. Click **Download** to install the integration.

#### **Step 4: Restart Home Assistant**

After installation, you need to restart Home Assistant for the integration to be recognized.

1. Go to **Settings** > **System** > **Restart**.
2. Click **Restart** and wait for Home Assistant to restart.

### Manual Installation

If you prefer to install the integration manually, follow these steps:

1. **Download the Integration**

   - Clone or download the `hass-panasonic-miraie` repository from GitHub.

2. **Copy to Home Assistant**

   - Place the `hass-panasonic-miraie` directory inside the `custom_components` directory of your Home Assistant configuration folder.
   - Your directory structure should look like this:

     ```tree
     └── config/
         ├── configuration.yaml
         └── custom_components/
          └── panasonic_miraie
              ├── __init__.py
              ├── api.py
              ├── climate.py
              ├── config_flow.py
              ├── const.py
              ├── icons
              │    └── logo.png
              ├── manifest.json
              ├── mqtt_handler.py
              └── translations
                  └── en.json
     ```

   - If the `custom_components` directory doesn't exist, create it.

3. **Restart Home Assistant**

   - After copying the files, restart Home Assistant to recognize the new integration.

## Configuration

1. In the Home Assistant UI, go to "Configuration" -> "Integrations".
2. Click the "+" button to add a new integration.
3. Search for "Panasonic MirAIe" and select it.
4. Enter your MirAIe account credentials (user ID/email and password).
5. The integration will automatically discover and add your MirAIe devices.

## Usage

After configuration, your Panasonic MirAIe devices will appear as climate entities in Home Assistant. You can control them through the Home Assistant UI, Lovelace cards, or include them in automations and scripts.

### Climate Entity Attributes

Each MirAIe device will have the following attributes:

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
- Check the Home Assistant logs for any error messages related to the Panasonic MirAIe integration.
- If you experience authentication problems, try to log out and log in again in the MirAIe mobile app, then reconfigure the integration in Home Assistant.

## Contributing

Contributions to improve the integration are welcome! Please feel free to submit pull requests or open issues for any bugs or feature requests on the [GitHub repository](https://github.com/chrissmartin/hass-panasonic-miraie).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This integration is not officially affiliated with or endorsed by Panasonic. Use at your own risk.
