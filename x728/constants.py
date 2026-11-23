"""Shared constants for the X728 integration."""

from typing import Final

DOMAIN: Final = "x728"
VERSION: Final = "2.0.0"
CONF_I2C_ADDRESS: Final = "i2c_address"
CONF_I2C_BUS: Final = "i2c_bus"
CONF_NAME: Final = "name"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_LOW_BATTERY: Final = "low_battery_threshold"
CONF_CHARGE_CONTROL: Final = "charge_control_gpio"
DEFAULT_NAME: Final = "X728 UPS"
DEFAULT_I2C_ADDRESS: Final = 0x36
DEFAULT_I2C_BUS: Final = 1
DEFAULT_SCAN_INTERVAL: Final = 30
DEFAULT_LOW_BATTERY: Final = 20

# X728 PLD is GPIO6, high when adapter power is lost. GPIO16 charge enable is
# only available on X728 V2.5; opt-in in the config flow after checking board.
PIN_POWER_LOSS: Final = 6
PIN_CHARGING: Final = 16
REG_VOLTAGE: Final = 0x02
REG_CAPACITY: Final = 0x04
CHARGE_LIMIT_FLOOR: Final = 20.0
DEFAULT_CHARGE_LIMIT_MIN: Final = 95.0
DEFAULT_CHARGE_LIMIT_MAX: Final = 100.0
DEFAULT_SHUTDOWN_BELOW: Final = 10.0
SHUTDOWN_BELOW_MIN: Final = 5.0
SHUTDOWN_BELOW_MAX: Final = 90.0
DEFAULT_SHUTDOWN_AFTER_MINUTES: Final = 0
SHUTDOWN_AFTER_MINUTES_MAX: Final = 240
SHUTDOWN_CONFIRM_SECONDS: Final = 60
SHUTDOWN_STARTUP_GRACE_SECONDS: Final = 180
RUNTIME_MIN_SECONDS: Final = 120
RUNTIME_MIN_DROP_PERCENT: Final = 0.5
RUNTIME_MAX_MINUTES: Final = 1440
BATTERY_STATES: Final = ["full", "high", "medium", "low", "critical"]
UPS_STATUSES: Final = ["online", "charging", "on_battery", "low_battery", "shutting_down"]
BATTERY_STATE_THRESHOLDS: Final = (95, 60, 30, 10)
EVENT_SHUTDOWN: Final = f"{DOMAIN}_shutdown"
STORAGE_KEY: Final = f"{DOMAIN}.settings"
STORAGE_VERSION: Final = 1
URL_BASE: Final = "/x728_static"
CARD_FILENAME: Final = "x728-ups-card.js"
