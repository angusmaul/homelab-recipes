# homelab-recipes

Reusable pieces from my home automation and homelab builds, most of them written up on
[Medium](https://geekconsulting.medium.com/). One folder per project. Every folder has a README
that says what it does, what to substitute, the assumptions that will bite you, how to check it
works, and what is and isn't proven yet.

They're written to be adapted by people **and by AI agents**. Each README ends with a short
*For AI agents* list: discover the real entity IDs, check units and sign conventions against
live readings, dry-run first, and prove every action against the device itself rather than
trusting a success response.

| Folder | What it does |
|---|---|
| [spa-solar-heating](spa-solar-heating/) | Heat a Bestway spa in Home Assistant only on spare solar, with a Tesla Powerwall getting first call. [Article](https://geekconsulting.medium.com/a-spring-scorcher-a-powerwall-and-a-spa-that-only-heats-on-spare-sunshine-c2c1dc44efc1) |
| [tesla-plug-in-alert](tesla-plug-in-alert/) | Push to your phone when charging the car would be free or cheap and it isn't plugged in. [Article](https://geekconsulting.medium.com/the-someday-project-part-iii-the-homelab-paid-for-itself-in-one-push-notification-455558316369) |
| [petlibro-feeder](petlibro-feeder/) | "Hey Google, feed the cat" for a PetLibro feeder: fails loudly, never over-dispenses, and self-heals the integration after a bad boot |
| [karaoke-tidy](karaoke-tidy/) | File the songs guests add to a PiKaraoke library from their phones, each night, with n8n and two local Ollama models that have to agree on the language |

Placeholders look like `__UPPER_SNAKE__`; `grep -o "__[A-Z_]*__"` finds any left.

Every pull request gets an automated Claude review focused on privacy and secrets (see
[claude-review.yml](.github/workflows/claude-review.yml)) and a gitleaks scan, on top of GitHub's
secret scanning and push protection.

MIT licensed. No warranty: these run real equipment, so read the README before you run anything.
