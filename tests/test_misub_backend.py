"""Offline artifact checks; MISUB_SOURCE enables the actual MiSub renderer.

Set MIHOMO_BIN too to verify native backend output with local UDP packets.
"""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest

import test_runtime


ROOT = Path(__file__).resolve().parents[1]
SOURCE = os.environ.get("MISUB_SOURCE")
spec = importlib.util.spec_from_file_location("misub_builder", ROOT / "tools/build_misub.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def render(template, **options):
    result = subprocess.run(["node", str(ROOT / "tests/misub_bridge.mjs")],
                            input=json.dumps({"template": template, "options": options}),
                            capture_output=True, text=True, encoding="utf-8", timeout=15, check=True)
    return json.loads(result.stdout)


class MiSubArtifactTests(unittest.TestCase):
    def test_generated_native_template_is_current_and_has_adjacent_guards(self):
        text = (ROOT / "acl4ssr-ai-chain-misub.ini").read_text(encoding="utf-8")
        self.assertEqual(text, builder.build((ROOT / "acl4ssr-ai-chain-v2.ini").read_text(encoding="utf-8-sig")))
        self.assertLess(len(text), 128 * 1024)
        rules = [line for line in text.splitlines() if line.startswith("ruleset=")]
        for index, line in enumerate(rules):
            policy, source = line[len("ruleset="):].split(",", 1)
            if policy not in ("DIRECT", "REJECT", "REJECT-DROP"):
                self.assertEqual(rules[index + 1], "ruleset=REJECT," + source)
        self.assertNotIn("quanx:", text)
        self.assertNotIn("[]AND,", text)
        self.assertNotIn("[]IP-CIDR", text)
        self.assertIn(builder.RAW_BASE + "rules/cn-ip-fallback.list", text)

    def test_native_ai_provider_is_classical_and_excludes_process_rules(self):
        rules = [line for line in (ROOT / "rules/overseas-ai.list").read_text(encoding="utf-8").splitlines()
                 if line and not line.startswith("#")]
        self.assertTrue(rules)
        for rule in rules:
            self.assertIn(rule.split(",")[0], ("DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD",
                                              "IP-CIDR", "IP-CIDR6", "IP-ASN"))


@unittest.skipUnless(SOURCE, "Set MISUB_SOURCE for actual backend generation checks")
class MiSubGenerationTests(unittest.TestCase):
    def test_full_template_preserves_guards_dns_groups_and_udp(self):
        import yaml
        dns = (ROOT / "configs/misub-dns.yaml").read_text(encoding="utf-8")
        config = render((ROOT / "acl4ssr-ai-chain-misub.ini").read_text(encoding="utf-8"),
                        nodeList="vless://00000000-0000-4000-8000-000000000001@proxy.example.com:443?security=tls&type=tcp#test-node",
                        enableUdp=True, customDnsOverride=dns)
        self.assertTrue(config["proxies"][0]["udp"])
        self.assertEqual(config["dns"], yaml.safe_load(dns)["dns"])
        targets = {proxy["name"] for proxy in config["proxies"]}
        targets.update(group["name"] for group in config["proxy-groups"])
        targets.update(("DIRECT", "REJECT"))
        for index, rule in enumerate(config["rules"]):
            fields = rule.split(",")
            target = fields[1] if fields[0] == "MATCH" else fields[2]
            self.assertIn(target, targets, rule)
            if target not in ("DIRECT", "REJECT"):
                guard = f"MATCH,REJECT" if fields[0] == "MATCH" else ",".join([*fields[:2], "REJECT"])
                self.assertEqual(config["rules"][index + 1], guard)
        self.assertEqual(config["rules"][-2:], ["MATCH,🐟 漏网之鱼", "MATCH,REJECT"])
        self.assertFalse(any(rule.startswith("AND,") for rule in config["rules"]))

    @unittest.skipUnless(test_runtime.CORE, "Set MIHOMO_BIN for native backend packet tests")
    def test_native_backend_output_blocks_udp_fallthrough_and_keeps_supported_udp(self):
        def convert(config):
            lines = ["[custom]", "custom_proxy_group=🤖 AI`select`[]tcp-only"]
            for rule in config["rules"]:
                fields = rule.split(",")
                target_index = 1 if fields[0] == "MATCH" else 2
                policy = fields.pop(target_index)
                source = "[]" + ",".join(fields)
                lines.append(f"ruleset={policy},{source}")
                if policy != "DIRECT":
                    lines.append(f"ruleset=REJECT,{source}")
            generated = render("\n".join(lines), proxies=config["proxies"], enableUdp=True,
                               customDnsOverride=json.dumps({"dns": config["dns"]}))
            return {**config, "rules": generated["rules"],
                    "proxy-groups": generated["proxy-groups"]}

        checker = test_runtime.RuntimeTests()
        for rule, host in (("DOMAIN-SUFFIX,claude.com,🤖 AI", "claude.com"),
                           ("DOMAIN,stun.l.google.com,🤖 AI", "stun.l.google.com"),
                           ("DOMAIN-KEYWORD,claude,🤖 AI", "claude.com"),
                           ("MATCH,🤖 AI", "127.0.0.1")):
            with self.subTest(rule=rule):
                checker.check_udp(rule, host, config_transform=convert)
        checker.check_udp("RULE-SET,protected,🤖 AI", "127.0.0.1", config_transform=convert,
                          providers={"protected": {"type": "inline", "behavior": "classical",
                                      "payload": ["IP-CIDR,127.0.0.1/32,no-resolve"]}})
        checker.check_udp("DOMAIN-SUFFIX,wechat.com,DIRECT", "wechat.com", expected_direct=True,
                          config_transform=convert)
        with test_runtime.udp_proxy() as (port, relay):
            checker.check_udp("DOMAIN-SUFFIX,claude.com,🤖 AI", "claude.com", proxy_port=port,
                              config_transform=convert)
            self.assertTrue(relay.recvfrom(4096)[0].endswith(b"routing-regression"))
        queries = []
        with test_runtime.dns_server("127.0.0.1") as domestic, \
                test_runtime.dns_server("127.0.0.1", queries) as overseas:
            checker.check_udp("RULE-SET,protected,🤖 AI", "wechat.com", expected_direct=True,
                              config_transform=convert,
                              providers={"protected": {"type": "inline", "behavior": "classical",
                                          "payload": ["IP-CIDR,203.0.113.8/32,no-resolve"]}},
                              dns={"enable": True, "ipv6": False, "nameserver": [overseas],
                                   "direct-nameserver": [domestic],
                                   "direct-nameserver-follow-policy": False})
        self.assertEqual(len(queries), 0, "Provider IP pins must retain no-resolve")


if __name__ == "__main__":
    unittest.main()
