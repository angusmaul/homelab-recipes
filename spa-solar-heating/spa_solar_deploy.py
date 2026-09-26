"""Push the spa solar automations + script (spa_solar.yaml) to Home Assistant, with a diff first.

    python spa_solar_deploy.py --set __SPA_CLIMATE__=climate.x --set __SPA_FILTER__=switch.y \
        --set __BATTERY_SOC__=sensor.z --set __NOTIFY_ENTITY__=notify.w            # diff only
    python spa_solar_deploy.py --set ... --apply                                   # write

Needs HA_URL (e.g. https://ha.example.com) and HA_TOKEN (a long-lived access token) in the
environment. The token is never printed.

Dry-run by default: prints a unified diff of each automation/script against the LIVE config.
Refuses if any __PLACEHOLDER__ is left unsubstituted, or if any entity the YAML references doesn't
exist in HA (the helpers must be created first; see helpers.yaml). Writes through HA's config API,
the same endpoint the automation editor uses, so the results are editable in the UI afterwards.
"""
import argparse
import difflib
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

import yaml

BASE = os.environ["HA_URL"].rstrip("/") + "/api"
HDR = {"Authorization": "Bearer " + os.environ["HA_TOKEN"], "Content-Type": "application/json"}
ENTITY = re.compile(r"\b(?:binary_sensor|climate|input_boolean|input_datetime|input_number|notify|"
                    r"script|sensor|sun|switch)\.[a-z0-9_]+\b")


def req(path, data=None, method="GET"):
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(BASE + path, data=body, headers=HDR, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        return e.code, None


def strings(node):
    """Every string in the config except `action:` values, which are services, not entities."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k != "action":
                yield from strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from strings(v)
    elif isinstance(node, str):
        yield node


def dump(obj):
    return yaml.safe_dump(obj, sort_keys=True,  # HA reorders keys on save; compare content only
                          allow_unicode=True, width=100).splitlines(keepends=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", action="append", default=[], metavar="__NAME__=entity_id")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    src = pathlib.Path(__file__).with_name("spa_solar.yaml").read_text(encoding="utf-8")
    for pair in a.set:
        key, _, val = pair.partition("=")
        src = src.replace(key, val)
    left = sorted(set(re.findall(r"__[A-Z_]+__", src)))
    if left:
        sys.exit(f"refusing: unsubstituted placeholders {left}")
    cfg = yaml.safe_load(src)

    own_scripts = {"script." + k for k in cfg["scripts"]}
    refs = set()
    for text in strings(cfg):
        refs.update(ENTITY.findall(text))
    missing = []
    for eid in sorted(refs - own_scripts):
        code, st = req("/states/" + eid)
        if code != 200:
            missing.append(eid)
        else:
            print(f"ok  {eid} = {st['state']}")
    if missing:
        sys.exit(f"refusing: not found in HA: {missing}")

    items = [("automation", x["id"], x) for x in cfg["automations"]]
    items += [("script", k, v) for k, v in cfg["scripts"].items()]
    for kind, oid, body in items:
        code, live = req(f"/config/{kind}/config/{oid}")
        live = live if code == 200 else {}
        diff = list(difflib.unified_diff(dump(live), dump(body), f"live/{kind}/{oid}", f"repo/{kind}/{oid}"))
        print(f"\n=== {kind} {oid}: {'NEW' if not live else ('changed' if diff else 'unchanged')}")
        sys.stdout.writelines(diff)
        if a.apply and diff:
            code, resp = req(f"/config/{kind}/config/{oid}", body, "POST")
            print(f"--> POST {code} {resp}")
            if code != 200:
                sys.exit("write failed")
    if not a.apply:
        print("\n(dry run -- re-run with --apply to write)")


if __name__ == "__main__":
    main()
