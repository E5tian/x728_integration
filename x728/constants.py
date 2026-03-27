DOMAIN = "x728"

CONF_I2C_ADDRESS = "i2c_address"
CONF_I2C_BUS = "i2c_bus"
CONF_NAME = "name"

DEFAULT_NAME = "X728 Sensor"
DEFAULT_I2C_ADDRESS = 0x36
DEFAULT_I2C_BUS = 1

SENSOR_VOLTAGE = "voltage"
SENSOR_CAPACITY = "capacity"

SENSOR_TYPES = {
    SENSOR_VOLTAGE: {
        "name": "Voltage",
        "unit": "V",
        "device_class": "voltage",
    },
    SENSOR_CAPACITY: {
        "name": "Capacity",
        "unit": "%",
        "device_class": "battery",
    },
}

DEFAULT_MONITORED = [SENSOR_VOLTAGE, SENSOR_CAPACITY]