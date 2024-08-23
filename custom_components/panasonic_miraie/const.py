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
