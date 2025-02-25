"""Constants for the Panasonic MirAIe integration."""

DOMAIN = "panasonic_miraie"

CONF_USER_ID = "user_id"
CONF_PASSWORD = "password"

MIRAIE_AUTH_API_BASE_URL = "https://auth.miraie.in/simplifi/v1"
MIRAIE_APP_API_BASE_URL = "https://app.miraie.in/simplifi/v1"
MIRAIE_BROKER_HOST = "mqtt.miraie.in"
MIRAIE_BROKER_PORT = 8883
MIRAIE_BROKER_USE_SSL = True

# 360 sec = 6 min
LOGIN_RETRY_DELAY = 360 * 1000

# Used to renew the token periodically. Only a safety measure, since we are handling
# network errors dynamically and re-issuing a login upon a 401 Unauthorized error.
# 604,800 sec = 7 days
LOGIN_TOKEN_REFRESH_INTERVAL = 604800 * 1000

# MQTT connection parameters
MQTT_KEEPALIVE = 60  # 60 seconds
MQTT_CONNECTION_TIMEOUT = 10  # 10 seconds
MQTT_RECONNECT_INTERVAL = 60  # Check connection every 60 seconds

# API request timeouts
API_TIMEOUT = 15  # 15 seconds
API_COMMAND_TIMEOUT = 5  # 5 seconds for commands

# Climate entity parameters
CLIMATE_UPDATE_INTERVAL = 300  # 5 minutes
CLIMATE_COMMAND_RETRY = 2  # Number of retries for climate commands
