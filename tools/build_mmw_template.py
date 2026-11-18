#!/usr/bin/env python3
"""Port the ACL4SSR INI into the Clash YAML template that miaomiaowu (mmw) expects.

mmw's "rule template" slot parses its file as YAML. Feeding it the INI fails with
``yaml: line 5: mapping values are not allowed in this context`` and mmw silently
falls back to the raw subscription file, so the client keeps the previous rules.
This script keeps one routing template: the INI stays the source of truth and the
YAML only carries the compiled rule list.

Only the ``rules:`` block is regenerated. Every other byte — port, DNS, proxies,
groups and rule-providers — is copied from the reference config, so the template
keeps working group and provider references.

Usage:
  python tools/build_mmw_template.py --base mirage.yaml
  python tools/build_mmw_template.py --base mirage.yaml -o my_clash.yaml

``--base`` is the Clash config currently served for the subscription, i.e.
``/opt/mmw/subscribes/<name>.yaml`` on the mmw host. Pull it once per layout
change:

  ssh <host> "cat /opt/mmw/subscribes/mirage.yaml" > mirage.yaml

Rule mapping:
  ruleset=GROUP,[]DOMAIN-SUFFIX,example.com   -> DOMAIN-SUFFIX,example.com,GROUP
  ruleset=GROUP,[]FINAL                       -> MATCH,GROUP
  ruleset=GROUP,https://.../Google.list       -> RULE-SET,Google,GROUP
  The rule-set tag comes from the base config's rule-providers (matched by URL),
  never from the filename, so ``cncidr.txt`` and ``Google.list`` both resolve.
"""

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INI = ROOT / "acl4ssr-ai-chain-v2.ini"


def ini_rulesets(text):
    rules = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("ruleset="):
            continue
        policy, source = line[len("ruleset="):].split(",", 1)
        rules.append((policy.strip(), source.strip()))
    return rules


def provider_urls(yaml_text):
    """tag -> url, read from the base config's rule-providers block."""
    block = yaml_text.split("\nrule-providers:\n", 1)[1]
    tags = {}
    name = None
    for line in block.splitlines():
        match = re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", line)
        if match:
            name = match.group(1)
            continue
        match = re.match(r"^    url:\s*(\S+)\s*$", line)
        if match and name:
            tags[name] = match.group(1)
            name = None
    return tags


def compile_rules(rulesets, url_to_tag):
    compiled, missing = [], []
    for policy, source in rulesets:
        if source.startswith("[]"):
            body = source[2:]
            compiled.append(f"  - MATCH,{policy}" if body in ("FINAL", "MATCH")
                            else f"  - {body},{policy}")
            continue
        tag = url_to_tag.get(source)
        if tag is None:
            missing.append(source)
            tag = source.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        compiled.append(f"  - RULE-SET,{tag},{policy}")
    return compiled, missing


def strip_proxies(text):
    """Blank the proxies block.

    mmw replaces proxies with its own node table on every render (verified: a
    template carrying three nodes still renders four), so the template does not
    need them — and the published copy must not carry node credentials.
    """
    start = text.index("\nproxies:\n") + 1
    end = text.index("\nproxy-groups:\n") + 1
    return text[:start] + "proxies: []\n" + text[end:]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ini", type=Path, default=INI)
    parser.add_argument("--base", type=Path, required=True,
                        help="Clash config used as the skeleton (mmw subscribes/*.yaml)")
    parser.add_argument("--strip-proxies", action="store_true",
                        help="replace the node list with 'proxies: []' before publishing")
    parser.add_argument("-o", "--output", type=Path, default=Path("my_clash.yaml"))
    args = parser.parse_args()

    ini_text = args.ini.read_text(encoding="utf-8-sig")
    base_text = args.base.read_text(encoding="utf-8-sig")
    if "\nrules:\n" not in base_text or "\nrule-providers:\n" not in base_text:
        raise SystemExit(f"{args.base} has no rules/rule-providers block to replace")

    rulesets = ini_rulesets(ini_text)
    url_to_tag = {url: tag for tag, url in provider_urls(base_text).items()}
    compiled, missing = compile_rules(rulesets, url_to_tag)
    if missing:
        raise SystemExit("base config has no rule-providers for:\n  " + "\n  ".join(missing))

    head, rest = base_text.split("\nrules:\n", 1)
    _, tail = rest.split("\nrule-providers:\n", 1)
    output = head + "\nrules:\n" + "\n".join(compiled) + "\nrule-providers:\n" + tail
    if args.strip_proxies:
        output = strip_proxies(output)
    args.output.write_text(output, encoding="utf-8", newline="\n")

    print(f"{len(rulesets)} rulesets -> {len(compiled)} rules")
    print(f"wrote {args.output} ({args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
