# homelab-recipes

Reusable pieces from my home automation and homelab builds, each one written up on
[Medium](https://geekconsulting.medium.com/). One folder per project. Every folder has a README
that says what it does, what to substitute, the assumptions that will bite you, how to check it
works, and what is and isn't proven yet.

They're written to be adapted by people **and by AI agents**. Each README ends with a short
*For AI agents* list: discover the real entity IDs, check units and sign conventions against
live readings, dry-run first, and prove every action against the device itself rather than
trusting a success response.

| Folder | What it does |
|---|---|
| [spa-solar-heating](spa-solar-heating/) | Heat a Bestway spa in Home Assistant only on spare solar, with a Tesla Powerwall getting first call |

Placeholders look like `__UPPER_SNAKE__`; `grep -o "__[A-Z_]*__"` finds any left.

MIT licensed. No warranty: these run real equipment, so read the README before you run anything.
