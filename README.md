# Geekworm X728 UPS for Home Assistant

Home Assistant integration for monitoring a Geekworm X728 UPS. It reports battery voltage and capacity, AC loss, outage history, runtime estimates, and provides configurable automatic shutdown. X728 V2.5 boards can optionally enable charging control and charge-window limits via GPIO16.

## Features

- Battery level, voltage, AC power, charging state, battery state and UPS status
- Power outage/restoration timestamps and count
- Runtime estimate learned from measured outages
- Optional charge enable switch and configurable charge window (X728 V2.5 only)
- Opt-in automatic host shutdown on low battery or prolonged outage
- Lovelace dashboard card: `custom:x728-ups-card`

## Installation and setup

Copy `x728/` into Home Assistant's `custom_components/` directory as `x728`, restart Home Assistant and add **Geekworm X728 UPS** under Settings → Devices & services.

Enable I2C and verify the fuel gauge is reachable at the configured I2C bus/address. Power-loss detection uses GPIO6 (PLD); the PLD jumper must be enabled. The integration polls at the configured interval and reacts immediately to GPIO edge events.

**Important:** Enable “GPIO charging control” only for X728 V2.5 hardware with the appropriate CHG control jumper configuration. GPIO16 has different board-revision support and should not be claimed by this integration on earlier models. Charging remains untouched by default on unsupported revisions.

## Shutdown safety

Automatic shutdown is disabled by default. When enabled, Home Assistant waits for its startup grace period and then requires the condition to persist for one minute. Restored mains power cancels the countdown. Home Assistant OS/Supervised uses `hassio.host_shutdown`; other installations receive the `x728_shutdown` event so an automation can handle shutdown. Test your board and configuration before relying on this for unattended power loss.

## Dashboard

The card is registered as frontend JavaScript during integration setup. Add it to a dashboard:

```yaml
type: custom:x728-ups-card
name: Rack UPS
```

MIT License.
