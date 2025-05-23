"""Constants for the Panasonic MirAIe integration."""

DOMAIN = "panasonic_miraie"

CONF_USER_ID = "user_id"
CONF_PASSWORD = "password"

MIRAIE_AUTH_API_BASE_URL = "https://auth.miraie.in/simplifi/v1"
MIRAIE_APP_API_BASE_URL = "https://app.miraie.in/simplifi/v1"
MIRAIE_BROKER_HOST = "mqtt.miraie.in"
MIRAIE_BROKER_PORT = 8883
MIRAIE_BROKER_USE_SSL = True

# Preset mode constants
PRESET_NONE = "none"
PRESET_NANOE = "nanoe"
PRESET_POWERFUL = "powerful"
PRESET_ECONOMY = "economy"
PRESET_CLEAN = "clean"
PRESET_NANOE_POWERFUL = "nanoe_powerful"
PRESET_NANOE_ECONOMY = "nanoe_economy"

PRESET_CONVERTI7_HC = "converti7_hc"
PRESET_CONVERTI7_FC = "converti7_fc"
PRESET_CONVERTI7_90 = "converti7_90"
PRESET_CONVERTI7_80 = "converti7_80"
PRESET_CONVERTI7_70 = "converti7_70"
PRESET_CONVERTI7_55 = "converti7_55"
PRESET_CONVERTI7_40 = "converti7_40"
PRESET_CONVERTI7_OFF = "converti7_off"

# Preset mode definitions with friendly names and icons
PRESET_MODES = {
    PRESET_NONE: {"name": "None", "icon": "mdi:cancel"},
    PRESET_NANOE: {"name": "Nanoe G", "icon": "mdi:air-purifier"},
    PRESET_POWERFUL: {"name": "Powerful", "icon": "mdi:rocket-launch"},
    PRESET_ECONOMY: {"name": "Economy", "icon": "mdi:leaf"},
    PRESET_CLEAN: {"name": "Clean", "icon": "mdi:broom"},
    PRESET_NANOE_POWERFUL: {
        "name": "Nanoe + Powerful",
        "icon": "mdi:weather-windy",
    },
    PRESET_NANOE_ECONOMY: {
        "name": "Nanoe + Economy",
        "icon": "mdi:leaf-circle-outline",
    },
    PRESET_CONVERTI7_HC: {
        "name": "Converti7 HC",
        "icon": "mdi:arrow-up-bold-hexagon-outline",
    },
    PRESET_CONVERTI7_FC: {
        "name": "Converti7 FC",
        "icon": "mdi:arrow-up-bold-box-outline",
    },
    PRESET_CONVERTI7_90: {"name": "Converti7 90%", "icon": "mdi:fraction-one-half"},
    PRESET_CONVERTI7_80: {"name": "Converti7 80%", "icon": "mdi:fraction-one-half"},
    PRESET_CONVERTI7_70: {"name": "Converti7 70%", "icon": "mdi:fraction-one-half"},
    PRESET_CONVERTI7_55: {"name": "Converti7 55%", "icon": "mdi:fraction-one-half"},
    PRESET_CONVERTI7_40: {"name": "Converti7 40%", "icon": "mdi:fraction-one-half"},
    PRESET_CONVERTI7_OFF: {
        "name": "Converti7 Off",
        "icon": "mdi:power-plug-off-outline",
    },
}

# 360 sec = 6 min
LOGIN_RETRY_DELAY = 360 * 1000

# Used to renew the token periodically. Only a safety measure, since we are handling
# network errors dynamically and re-issuing a login upon a 401 Unauthorized error.
# 604,800 sec = 7 days
LOGIN_TOKEN_REFRESH_INTERVAL = 604800 * 1000

# MQTT connection parameters
MQTT_KEEPALIVE = 30  # 30 seconds (smaller value than default)
MQTT_CONNECTION_TIMEOUT = 10  # 10 seconds
MQTT_RECONNECT_INTERVAL = 60  # Check connection every 60 seconds
MQTT_PING_INTERVAL = 45  # Send ping every 45 seconds to keep connection alive

# API request timeouts
API_TIMEOUT = 15  # 15 seconds
API_COMMAND_TIMEOUT = 5  # 5 seconds for commands

# Climate entity parameters
CLIMATE_UPDATE_INTERVAL = 300  # 5 minutes
CLIMATE_COMMAND_RETRY = 2  # Number of retries for climate commands
