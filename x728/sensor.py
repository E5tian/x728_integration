import struct
import logging
from time import sleep
from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass
from homeassistant.helpers.entity import Entity
from .constants import DOMAIN, SENSOR_TYPES, SENSOR_VOLTAGE, SENSOR_CAPACITY

_LOGGER = logging.getLogger(__name__)


def _setup_x728(i2c_address, i2c_bus):
    """Initialize the X728 hardware and handler in an executor thread."""
    from smbus import SMBus

    sensor = X728(i2c_address, SMBus(i2c_bus))
    return sensor, X728Handler(sensor)


async def async_setup_entry(hass, entry, async_add_entities):
    i2c_address = entry.data["i2c_address"]
    i2c_bus = entry.data["i2c_bus"]
    name = entry.data.get("name", "X728 Sensor")

    # SMBus access is synchronous; keep it off Home Assistant's event loop.
    sensor, handler = await hass.async_add_executor_job(
        _setup_x728, i2c_address, i2c_bus
    )

    entities = [
        X728Sensor(handler, sensor_type, name)
        for sensor_type in [SENSOR_VOLTAGE, SENSOR_CAPACITY]
    ]
    async_add_entities(entities, True)


class X728Sensor(SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, handler, sensor_type, name):
        self._handler = handler
        self._type = sensor_type
        self._attr_name = f"{name} {SENSOR_TYPES[sensor_type]['name']}"
        self._attr_unique_id = f"x728_{sensor_type}"
        self._attr_native_unit_of_measurement = SENSOR_TYPES[sensor_type]["unit"]
        self._attr_device_class = SENSOR_TYPES[sensor_type]["device_class"]
        self._attr_device_info = {
            "identifiers": {("geekworm", "x728")},
            "name": "Geekworm X728 UPS",
            "manufacturer": "Geekworm",
            "model": "X728",
        }

    async def async_update(self):
        await self.hass.async_add_executor_job(self._handler.update)
        if self._type == SENSOR_VOLTAGE:
            self._attr_native_value = round(self._handler.sensor_data.voltage, 1)
        elif self._type == SENSOR_CAPACITY:
            self._attr_native_value = round(self._handler.sensor_data.capacity, 1)


class X728Handler:
    class SensorData:
        def __init__(self):
            self.voltage = None
            self.capacity = None

    def __init__(self, sensor):
        self.sensor_data = self.SensorData()
        self._sensor = sensor
        self.update(first_read=True)

    def update(self, first_read=False):
        if first_read:
            self._sensor.get_sensor_data()
        if self._sensor.get_sensor_data():
            self.sensor_data.voltage = self._sensor.data.voltage
            self.sensor_data.capacity = self._sensor.data.capacity


class FieldData:
    def __init__(self):
        self.voltage = None
        self.capacity = None
        self.status = None


class X728Data:
    def __init__(self):
        self.data = FieldData()


class X728(X728Data):
    def __init__(self, i2c_addr=0x36, i2c_device=None):
        super().__init__()
        self.i2c_addr = i2c_addr
        self._i2c = i2c_device
        if self._i2c is None:
            import smbus
            self._i2c = smbus.SMBus(1)
        self.get_sensor_data()

    def get_sensor_data(self):
        read = self._i2c.read_word_data(self.i2c_addr, 2)
        swapped = struct.unpack("<H", struct.pack(">H", read))[0]
        self.data.voltage = swapped * 1.25 / 1000 / 16
        read = self._i2c.read_word_data(self.i2c_addr, 4)
        swapped = struct.unpack("<H", struct.pack(">H", read))[0]
        self.data.capacity = swapped / 256
        return True
