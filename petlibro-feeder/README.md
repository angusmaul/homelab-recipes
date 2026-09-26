# "Hey Google, feed the cat": PetLibro feeder in Home Assistant

A voice-callable feed script for a PetLibro Granary feeder that **fails loudly instead of silently**, plus
a self-heal automation that revives the integration after the boot-time failure it's prone to. Not
written up on Medium; notes are below.

## Status

Running since 2026-08-09, hardened 2026-08-21 after a real silent failure. **Proven live:** voice feeding
through Google (2 portions measured at exactly 40.0 mL / 20 g), the loud-failure path, and the
portion-confirm wait. Both files are copied from the live install.

## Files

| File | What it is |
|---|---|
| `feed_the_cat.yaml` | `script.feed_the_cat`: sets the portion, confirms it took, then dispenses. Refuses and notifies on any doubt |
| `petlibro_self_heal.yaml` | Reloads the integration when a boot-time DNS race leaves it stuck at `setup_error` |

## Requirements

- [Home Assistant](https://www.home-assistant.io/).
- [jjjonesjr33/petlibro](https://github.com/jjjonesjr33/petlibro). It's in the **default** HACS index,
  so don't add it as a custom repository, whatever most guides say.
- Built on a **PLAF103 v2 (Granary)**. That model has **no local control**: no listening ports at all,
  including Tuya's 6668, and [petlibro-esphome](https://github.com/taylorfinnell/petlibro-esphome)
  doesn't support it. Cloud only. Scheduled meals run on the device itself, so the cat still eats if
  HA or the internet is down.
- [ntfy](https://www.home-assistant.io/integrations/ntfy/) for the failure pushes.
- For voice: Home Assistant Cloud (Nabu Casa) with Google Assistant.

## Substitute these

| Placeholder | In | What it is |
|---|---|---|
| `__NOTIFY_ENTITY__` | both | an ntfy notify entity |
| `__HA_URL__` | both | a URL for your HA that works from your phone (the failure push links to the integration page) |
| `__PETLIBRO_ENTRY_ID__` | self-heal | the PetLibro config entry ID (on the integration's entry page) |

The `granary_smart_feeder_*` entity IDs are what the integration creates for a feeder named "Granary
Smart Feeder". If yours is named differently, replace the prefix throughout.

## Assumptions that bite

- **One portion is 1/12 US cup, about 20 mL, not 10.** A default of 4 "because the meal is 40 mL" would
  double every meal. Derive portions from `volume / 19.7`.
- **One PetLibro session per account.** Signing HA in with your main account kicks the phone app out,
  and vice versa, forever. Make a second account, share the feeder to it, and give that one to HA.
- **`button.*` entities read `unknown` until first pressed.** That's normal. `unavailable` is the
  fault signal.
- **Index the portion options, and clamp the index.** The options are Unicode fraction glyphs, so the
  script looks them up by position. Jinja uses Python indexing: an unclamped `portions=0` resolves to
  `[-1]`, the *last* option, which is **4 cups**.
- **`select.select_option` updates HA's state optimistically.** The confirm-wait passes instantly, so
  the 3 s delay for the cloud round-trip is kept as well.
- **The integration's boot failure is never retried by HA.** It raises a plain setup error rather than
  `ConfigEntryNotReady` when DNS isn't ready, which is what the self-heal is for. Only `unavailable`
  means the integration is dead. A feeder that's merely offline reads `off`, so don't widen the check.
- **Cloud round-trip is ~33 s** from the service call to visible state. Don't judge a feed failed inside
  a minute.

## Install

1. Add the integration with the **second** PetLibro account.
2. Create `script.feed_the_cat` from `feed_the_cat.yaml` (script ID `feed_the_cat`), substituted.
3. Add `petlibro_self_heal.yaml` as an automation, substituted.
4. For voice: expose the script to Google Assistant, then link from the **Google Home app** (Devices →
   Add → Works with Google Home → Home Assistant). Enabling Google in the HA Cloud settings alone links
   nothing. Google treats a script as a scene: *"Hey Google, activate Feed the cat."*
5. For a dashboard: give the script an **area**. Area-strategy dashboards don't render buttons as
   tappable tiles, but a script with an area shows up as one.

## Verify it works

- Run the script at 2 portions with someone at the bowl: check `last_feed_quantity` reads about 40 mL
  and today's feeding count goes up by one, about 30 s later.
- Unplug the feeder's power and run it: you should get the *FAILED* push, and nothing is dispensed.

## For AI agents

1. Discover the real entity IDs and the config entry ID from the running HA.
2. **Never test by dispensing without a human confirming the bowl.** This feeds an animal.
3. Derive portion volume from a measured feed, not an assumed per-portion figure.
4. Treat `unknown` on buttons as normal; diagnose from `unavailable`.
5. Keep both the 3 s delay and the confirm-wait, in that order. Never demote the loud-failure `stop` back
   to a plain condition.
6. Never print or commit the PetLibro account credentials or the HA token.

## License

MIT. See [LICENSE](../LICENSE).
