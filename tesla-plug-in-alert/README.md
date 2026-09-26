# Tesla "plug me in" alert

A Home Assistant push to your phone when charging the car would be free or cheap and it isn't plugged
in: spare solar with the home battery already nearly full, or a grid price under 10 c/kWh. Written up on
Medium: [The Homelab Paid For Itself In One Push Notification](https://geekconsulting.medium.com/the-someday-project-part-iii-the-homelab-paid-for-itself-in-one-push-notification-455558316369).

## Status

Running since 2026-07-12. **Proven live:** real pushes on real opportunities, the double-push race fixed
(2026-07-15), and presence verified both ways (away with every economic gate met, and no push; home,
and it tracks solar honestly). The opportunity sensor YAML is written from the documented logic rather
than exported from the UI helper. On 2026-09-26 it agreed with the live helper (both off), which only exercises the off case, so treat it as reviewed rather than fully run.

## Files

| File | What it is |
|---|---|
| `opportunity_sensor.yaml` | The template binary sensor holding every threshold. On the original install it's a UI helper |
| `automation.yaml` | The alert: 10-minute sustain, 2-hourly reminders, and the guard that stops them racing. Copied from the live automation |

## Requirements

- [Home Assistant](https://www.home-assistant.io/) (built on 2026.7).
- [Tessie](https://www.home-assistant.io/integrations/tessie/) for the car's charge cable and battery
  level, and the Powerwall's solar and charge. Any integration with the same readings works.
- [Amber Electric](https://www.home-assistant.io/integrations/amberelectric/) for the price (optional;
  Australia only). Without it, delete the price branch from the sensor.
- [ntfy](https://www.home-assistant.io/integrations/ntfy/): `ntfy.publish` carries the priority, tags
  and tap-through link.
- A **WiFi-based** presence tracker for the driver: the [UniFi Network](https://www.home-assistant.io/integrations/unifi/)
  integration, or your router's equivalent.

## Substitute these

| Placeholder | In | What it is |
|---|---|---|
| `__PERSON__` | sensor | the driver's `person.*` |
| `__CHARGE_CABLE__` | sensor | the car's charge-cable binary sensor (`on` = plugged in) |
| `__SOLAR_POWER__` | both | solar production |
| `__BATTERY_SOC__` | both | home battery charge, % |
| `__AMBER_GENERAL__` | both | Amber general price, $/kWh |
| `__CAR_BATTERY__` | automation | the car's battery level, % |
| `__NOTIFY_ENTITY__` | automation | an ntfy notify entity |
| `__HA_URL__` | automation | a URL for your HA that works from the phone **off** the LAN (the push's tap-through) |

`grep -o "__[A-Z_]*__" *.yaml` lists any left.

## Assumptions that bite

- **Units.** Tessie's solar power is **kW**. A threshold of `2000` would never fire.
- **Presence must come from WiFi association, not the phone app's GPS.** Without remote access, the
  app can't report location once the phone leaves the house, so its GPS tracker **freezes at `home`**
  and the alert fires while you're out. Even with remote access, keep it off the person: HA's `person`
  falls back to the latest GPS tracker whenever no non-GPS tracker reads `home`.
- **Exactly one tracker on the person**: the phone's real MAC. Turn off MAC randomisation for your home
  SSID. Extra trackers are not resilience: a UniFi entity can hold a stale `home` for a client the
  controller has already dropped, which pins presence at home forever.
- **Rename the Amber site and the price branch goes quiet.** The `float(999)` default disarms it
  rather than erroring, so nothing tells you.
- **The reminder guard is load-bearing.** Without the `> 600 s` check on the sensor's `last_changed`, a
  reminder tick can land just before the 10-minute sustain completes and you get two pushes 27 s apart.

## Install

1. Create the opportunity sensor (UI template helper, or `opportunity_sensor.yaml`) and check it
   against live state in **Developer tools → Template** before relying on it.
2. Paste `automation.yaml` as a new automation (Edit in YAML), substituted.
3. Test the push path with **Run actions** from the automation's menu, then wait for a real one.

## Verify it works

- Unplug the car on a sunny afternoon with the battery full: one push after 10 minutes, then nothing
  for 2 hours.
- Plug in: the sensor goes off, and there are no more reminders.
- Leave the house with the car unplugged and conditions met: **no** push (presence works).

## For AI agents

1. Discover the real entity IDs from the running Home Assistant; don't guess from the placeholders.
2. Check units live (kW vs W) before substituting thresholds.
3. Check which tracker drives the person and whether it's GPS. If it is, fix presence first: a working
   alert on broken presence notifies the user while they're away.
4. Evaluate the sensor template against live state before saving the automation.
5. Prove the push lands on the phone (or in ntfy's cache), not just that the service call returned.
6. Never print or commit the HA token or ntfy credentials.

## License

MIT. See [LICENSE](../LICENSE).
