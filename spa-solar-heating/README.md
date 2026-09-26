# Heat a Bestway spa on spare solar — battery first

Home Assistant automations that run a Bestway AirJet spa's heater only on solar power the house
would otherwise export, after the home battery (a Tesla Powerwall) has had first call, with a
15:30 comfort top-up and a filtration schedule. Written up on Medium (link to follow).

## Status

As of 2026-09-26. **Proven live:** control of the spa from HA (setpoint and heat on/off, checked in
the Bestway app, not just HA state); the heat-off rule firing on a real deficit and the filter rule
following it a minute later; target sync.
**Not yet proven:** heat-on from spare solar, the negative-price hold, the 15:30 floor, the
09:00/16:00 filter switches, restart persistence, and the offline alert. A trial is running. Treat
those paths as reviewed but untested.

## Files

| File | What it is |
|---|---|
| `helpers.yaml` | The helpers: master switch, thresholds, the Powerwall-aware *spare power* sensor and its 5-minute average, and two Amber price flags. ⚠️ Created in the UI on the original install; this YAML is the equivalent, written from the design, and hasn't been loaded as YAML there |
| `spa_solar.yaml` | Six automations and one script — the logic. Copied from the deployed file with house-specific IDs replaced by placeholders |
| `spa_solar_deploy.py` | Pushes `spa_solar.yaml` to HA through its config API. Dry-run diff by default |

## Requirements

- [Home Assistant](https://www.home-assistant.io/) (built on 2026.9.3).
- [ha-bestway](https://github.com/cdpuk/ha-bestway) v1.11.1, installed via [HACS](https://hacs.xyz/).
  Cloud-only. Tested on an AirJet with the V02 (AWS IoT) backend.
- [Tessie](https://www.home-assistant.io/integrations/tessie/) for the Powerwall's grid, battery and
  charge readings. Any integration works if it gives grid and battery power **from the same poll**.
- [Amber Electric](https://www.home-assistant.io/integrations/amberelectric/) for price flags
  (optional; Australia only). Without it, make the two binary sensors always `off`.
- A notifier for the offline alert (the original uses [ntfy](https://www.home-assistant.io/integrations/ntfy/)).
- Python 3 with PyYAML for the deploy script.

## Substitute these

| Placeholder | In | What it is | Example |
|---|---|---|---|
| `__SPA_CLIMATE__` | `spa_solar.yaml` | ha-bestway climate entity | `climate.airjet_spa_thermostat` |
| `__SPA_FILTER__` | `spa_solar.yaml` | ha-bestway filter pump switch | `switch.airjet_spa_filter` |
| `__BATTERY_SOC__` | both | battery charge, % | `sensor.<site>_percentage_charged` |
| `__NOTIFY_ENTITY__` | `spa_solar.yaml` | notify entity for the offline alert | `notify.<topic>` |
| `__GRID_POWER__` | `helpers.yaml` | grid power, + import / − export | `sensor.<site>_grid_power` |
| `__BATTERY_POWER__` | `helpers.yaml` | battery power, + discharging / − charging | `sensor.<site>_battery_power` |
| `__AMBER_GENERAL__` | `helpers.yaml` | Amber general (import) price | `sensor.<site>_general_price` |
| `__AMBER_FEED_IN__` | `helpers.yaml` | Amber feed-in price | `sensor.<site>_feed_in_price` |

`grep -o "__[A-Z_]*__" *.yaml` lists every one left.

## Assumptions that bite

- **Sign conventions.** The spare-power formula assumes grid **+ import / − export** and battery
  **+ discharging / − charging**. Check yours: at any moment, solar + battery + grid should equal
  the house load. If it doesn't balance, a sign is flipped.
- **Units.** Tessie reports **kW**; the formula works in W (`k = 1000` in the template). Set
  `k = 1` if your sensors report W. A threshold of 2400 against a kW sensor never fires.
- **One source, one poll.** Don't mix a local meter (e.g. an Enphase Envoy) with a cloud battery
  reading. They sample at different moments, and with a load that swings kilowatts minute to
  minute the difference is garbage (−8,721 W on a moment worth a few hundred).
- **Amber's feed-in sign.** HA's Amber integration multiplies feed-in by −1, so `< 0` means
  exporting *costs* money. [Source](https://github.com/home-assistant/core/blob/dev/homeassistant/components/amberelectric/sensor.py).
- **There is no heater switch** on the AirJet V02. The heater is the climate entity's `hvac_mode`
  (`heat` / `off`). Heat-on starts the filter pump; pump-off stops heating.
- **The water temperature lies briefly after a pump change.** It jumped 29 → 34 °C in 65 s as the
  pump stopped. Don't act on it for a few minutes after a pump start or stop.

## Install

1. **Add the spa with the app's *Share the device* QR code**, not the app's own user ID. Pasting the
   app's ID as the Visitor ID reads fine but every write fails with error 10001 —
   [cdpuk/ha-bestway#121](https://github.com/cdpuk/ha-bestway/issues/121). The QR gives HA its own
   guest identity, which shows in the app as an extra guest user; don't remove it. The QR grants
   control of the spa: decode it locally and don't paste it anywhere public.
2. **Prove control against the app.** Change the setpoint and toggle heat from HA and watch the
   Bestway app follow. HA's state changing isn't proof.
3. **Turn off any filter timer or heating schedule in the Bestway app.** It will fight HA: an app
   timer's pump-off kills heating mid-run. HA owns filtration from here.
4. **Create the helpers** (`helpers.yaml`, or the same IDs in the UI) and set their values.
5. **Check the signs and units** above against live readings.
6. **Dry run:** `HA_URL=… HA_TOKEN=… python spa_solar_deploy.py --set __SPA_CLIMATE__=… --set …`.
   It refuses on any unsubstituted placeholder or any entity HA doesn't have, then prints a diff.
7. **Apply:** the same with `--apply`. Re-run: everything should say `unchanged`.
8. Turn on `input_boolean.spa_solar_mode`.

## Verify it works

Check against the spa and the app, not HA's report of itself:

- **Heat on from spare solar:** on a sunny day with the battery ≥ 95 %, the heat-on rule fires, the
  app shows heating, and the battery does **not** start discharging for it.
- **Heat off when short:** the heat-off rule fires once the 5-minute spare is below −300 W and the
  heater has run 20 minutes.
- **No flapping:** nothing switches inside 20 minutes on or 10 minutes off.
- **Filter:** pump on at the window start, off at the end, except while heating (then off a minute
  after heat-off).
- **Restart:** restart HA; every helper keeps its value and every automation is on.

## For AI agents

1. Discover the real entity IDs from the running Home Assistant. Don't guess from the examples.
2. Verify the sign conventions and units against live readings (the energy-balance check above)
   before substituting. Never assume them.
3. Take grid and battery power from the same integration and poll.
4. Dry-run the deploy script and show the diff to your user before `--apply`.
5. Prove each action against the device itself — the Bestway app, or a power step on a quiet
   circuit. A 200 from HA is not proof the spa changed.
6. Never print or commit the share QR's contents or the HA token.
7. Turning `spa_solar_mode` off hands control back without touching the heater. If the heater was
   left in `heat`, the filter pump will keep running outside its window.

## License

MIT. See [LICENSE](../LICENSE).
