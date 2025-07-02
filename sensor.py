from homeassistant.components.sensor import SensorEntity
from homeassistant.const import TEMP_CELSIUS
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    devices = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for device in devices:
        # Skip devices that are not ACs if needed
        if device.device_type == "AC":
            entities.append(PanasonicTemperatureSensor(device, entry))

    async_add_entities(entities, True)

class PanasonicTemperatureSensor(SensorEntity):
    def __init__(self, device, entry):
        self._device = device
        self._attr_name = f"{device.name} Temperature"
        self._attr_unique_id = f"{device.serial}_temperature"
        self._attr_native_unit_of_measurement = TEMP_CELSIUS
        self._attr_device_class = "temperature"
        self._attr_state_class = "measurement"
        self._entry = entry

    @property
    def native_value(self):
        return float(self._device["rmtmp"]) if self._device.get("rmtmp") is not None else None

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self._device.serial)},
            name=self._device.name,
            manufacturer="Panasonic",
        )