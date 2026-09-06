"""Run offline: python -B -m unittest discover -s tests -v

Check live sources too: python -B tests/test_rules.py --online -v
Online checks require PyYAML. --cache-dir stores downloaded source snapshots.
--generated-yaml checks domain routing in actual subconverter output instead.
These are domain/process checks, not DNS, IP-resolution, or connectivity tests.
"""

import argparse
import hashlib
import ipaddress
import re
import sys
import time
import unittest
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "acl4ssr-ai-chain-v2.ini"
OVERRIDES = ROOT / "rules" / "cn-direct-override.list"
NODE = "\U0001f680 \u8282\u70b9\u9009\u62e9"
AI = "\U0001f916 AI"
MEDIA = "\U0001f3ac \u56fd\u5916\u6d41\u5a92\u4f53"
SOCIAL = "\U0001f310 \u56fd\u5916\u793e\u4ea4"
TELEGRAM = "\U0001f4f2 \u7535\u62a5\u6d88\u606f"
FALLBACK = "\U0001f41f \u6f0f\u7f51\u4e4b\u9c7c"
ONLINE = False
CACHE_DIR = None
GENERATED_YAML = None


def active_lines(text):
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(("#", ";", "//"))
    ]


def values(text, key):
    # Repeated INI keys are intentional in subconverter.
    prefix = key + "="
    return [line[len(prefix):] for line in active_lines(text) if line.startswith(prefix)]


def rulesets(text):
    return [tuple(value.split(",", 1)) for value in values(text, "ruleset")]


def source_type(source):
    for kind in ("surge", "clash-domain", "clash-ipcidr", "clash-classic"):
        if source.startswith(kind + ":"):
            return kind, source[len(kind) + 1:]
    return "surge", source


def fetch_text(url):
    request = Request(url, headers={"User-Agent": "clash-rules-self-tests"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8-sig")
        except OSError:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def first_match(rules, domain, process=None):
    domain = domain.lower().rstrip(".")
    for policy, rule in rules:
        kind, _, value = rule.partition(",")
        value = value.split(",", 1)[0]
        if kind in ("FINAL", "MATCH"):
            return policy
        if kind == "PROCESS-NAME" and process and value.lower() == process.lower():
            return policy
        if kind == "DOMAIN" and domain == value:
            return policy
        if kind == "DOMAIN-SUFFIX" and (domain == value or domain.endswith("." + value)):
            return policy
        if kind == "DOMAIN-KEYWORD" and value in domain:
            return policy
    return None


class ConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = CONFIG.read_text(encoding="utf-8-sig")
        cls.rules = rulesets(cls.text)
        cls.inline = [(policy, source[2:]) for policy, source in cls.rules if source.startswith("[]")]

    def position(self, suffix):
        matches = [i for i, (_, source) in enumerate(self.rules) if source.endswith(suffix)]
        self.assertEqual(len(matches), 1, suffix)
        return matches[0]

    def test_config_flags_and_targets(self):
        self.assertEqual(active_lines(self.text)[0], "[custom]")
        self.assertEqual(values(self.text, "enable_rule_generator"), ["true"])
        self.assertEqual(values(self.text, "overwrite_original_rules"), ["true"])
        groups = [value.split("`")[0] for value in values(self.text, "custom_proxy_group")]
        self.assertEqual(len(groups), len(set(groups)))
        for target, _ in self.rules:
            self.assertIn(target, [*groups, "DIRECT", "REJECT"])
        self.assertEqual(len(self.rules), len(set(self.rules)))

    def test_override_file_is_inlined_in_order(self):
        block = self.text.split("; BEGIN CN DIRECT OVERRIDES\n", 1)[1]
        block = block.split("; END CN DIRECT OVERRIDES", 1)[0]
        expected = [("DIRECT", "[]" + rule) for rule in active_lines(OVERRIDES.read_text(encoding="utf-8-sig"))]
        self.assertEqual(rulesets(block), expected)
        for _, source in expected:
            self.assertRegex(source, r"^\[\](PROCESS-NAME|DOMAIN|DOMAIN-SUFFIX),[^,]+$")

    def test_loyalsoldier_sources_are_surge_rulesets(self):
        expected = {"direct.txt", "gfw.txt", "cncidr.txt"}
        found = set()
        for _, source in self.rules:
            self.assertNotIn("clash-domain:", source)
            self.assertNotIn("clash-ipcidr:", source)
            if "/Loyalsoldier/" in source:
                kind, url = source_type(source)
                self.assertEqual(kind, "surge")
                self.assertIn("/Loyalsoldier/surge-rules/release/ruleset/", url)
                found.add(url.rsplit("/", 1)[-1])
        self.assertEqual(found, expected)

    def test_specific_services_precede_general_direct_rules(self):
        direct = self.position("/direct.txt")
        china = self.position("/ChinaDomain.list")
        for suffix in (",gvt1.com", ",gvt2.com", ",storage.googleapis.com",
                       "/global.list", "/YouTube.list", "/TikTok.list"):
            self.assertLess(self.position(suffix), min(direct, china), suffix)
        self.assertLess(self.position("/global.list"), self.position("/cn.list"))
        self.assertNotIn("/rules/surge/all.list", self.text)

    def test_google_and_ip_fallback_order(self):
        for suffix in ("/global.list", "/YouTube.list", "/GoogleCN.list"):
            self.assertLess(self.position(suffix), self.position("/Google.list"))
        for suffix in ("/ChinaCompanyIp.list", "/cncidr.txt", "[]GEOIP,CN,no-resolve"):
            self.assertLess(self.position("/gfw.txt"), self.position(suffix))
        self.assertEqual(self.rules[-1], (FALLBACK, "[]FINAL"))
        self.assertEqual(sum(source in ("[]FINAL", "[]MATCH") for _, source in self.rules), 1)
        fallback = next(group for group in values(self.text, "custom_proxy_group") if group.startswith(FALLBACK + "`"))
        self.assertEqual(fallback.split("`")[2], "[]DIRECT")

    def test_no_blanket_tencent_cloud_direct(self):
        for _, source in self.rules:
            self.assertNotIn("IP-ASN,132203", source)
            self.assertNotIn("/WeChat/WeChat.list", source)

    def test_inline_routes(self):
        cases = {
            "sdkinit.taobao.com": "DIRECT",
            "adash-c.m.taobao.com": "DIRECT",
            "servicewechat.com": "DIRECT",
            "api.bigmodel.cn": "DIRECT",
            "redirector.gvt1.com": NODE,
            "storage.googleapis.com": NODE,
            "stun.l.google.com": NODE,
            "stun.cloudflare.com": NODE,
            "global.stun.twilio.com": NODE,
            "anthropic.auth0.com": AI,
            "challenges.cloudflare.com": NODE,
            "www.recaptcha.net": NODE,
            "api.cloudflare.com": NODE,
            "d1.awsstatic.com": NODE,
            "browser-intake-datadoghq.com": NODE,
            "accounts.google.com": AI,
            "unrelated.auth0.com": NODE,
            "unmatched.example": FALLBACK,
        }
        for domain, expected in cases.items():
            with self.subTest(domain=domain):
                self.assertEqual(first_match(self.inline, domain), expected)
        for process in ("WeChat.exe", "Weixin", "com.tencent.mm", "com.taobao.taobao"):
            with self.subTest(process=process):
                self.assertEqual(first_match(self.inline, "stun.l.google.com", process), "DIRECT")
        self.assertEqual(first_match(self.inline, "api.snssdk.com", "com.zhiliaoapp.musically"), MEDIA)


class LiveRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ONLINE and not GENERATED_YAML:
            raise unittest.SkipTest("Use --online or --generated-yaml for expanded domain checks")
        import yaml

        def load(text):
            return yaml.load(text, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))

        cls.expanded = []
        if GENERATED_YAML:
            config = load(GENERATED_YAML.read_text(encoding="utf-8-sig"))
            for rule in config["rules"]:
                parts = rule.split(",")
                if parts[0] in ("FINAL", "MATCH"):
                    cls.expanded.append((parts[1], parts[0]))
                else:
                    cls.expanded.append((parts[2], ",".join(parts[:2])))
            return

        failures = []
        sources = 0
        for policy, source in rulesets(CONFIG.read_text(encoding="utf-8-sig")):
            if source.startswith("[]"):
                cls.expanded.append((policy, source[2:]))
                continue
            kind, url = source_type(source)
            try:
                text = fetch_text(url)
                if CACHE_DIR:
                    CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    name = hashlib.sha256(url.encode()).hexdigest()[:16] + ".txt"
                    (CACHE_DIR / name).write_text(text, encoding="utf-8", newline="")
                if kind.startswith("clash-"):
                    payload = load(text)["payload"]
                    if not isinstance(payload, list) or not payload:
                        raise ValueError("Expected a nonempty YAML payload list")
                    entries = []
                    for value in payload:
                        if kind == "clash-domain":
                            prefix = "DOMAIN,"
                            if value.startswith("+."):
                                prefix, value = "DOMAIN-SUFFIX,", value[2:]
                            elif value.startswith("."):
                                prefix, value = "DOMAIN-SUFFIX,", value[1:]
                            entries.append(prefix + value)
                        elif kind == "clash-ipcidr":
                            entries.append(("IP-CIDR6," if ":" in value else "IP-CIDR,") + value)
                        else:
                            entries.append(value)
                else:
                    entries = active_lines(text)
                    if not entries or any(not re.match(r"^[A-Z][A-Z0-9-]*,", entry) for entry in entries):
                        raise ValueError("Expected a plain rule list, not YAML or HTML")
                cls.expanded.extend((policy, entry) for entry in entries)
                sources += 1
                print("OK", kind, url.rsplit("/", 1)[-1], len(entries), flush=True)
            except Exception as error:
                failures.append(f"{url}: {error}")
        if failures:
            raise AssertionError("\n".join(failures))
        print(f"Validated {sources} remote sources; expanded {len(cls.expanded)} rules.", flush=True)

    def test_expanded_payload_syntax(self):
        for _, rule in self.expanded:
            kind, _, payload = rule.partition(",")
            value = payload.split(",", 1)[0]
            if kind in ("DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD"):
                self.assertNotRegex(value, r"""['"\s]""", rule)
                self.assertFalse(value.startswith("+."), rule)
            elif kind in ("IP-CIDR", "IP-CIDR6"):
                network = ipaddress.ip_network(value, strict=False)
                self.assertEqual(network.version, 6 if kind == "IP-CIDR6" else 4, rule)

    def test_domain_routes(self):
        cases = {
            "sdkinit.taobao.com": "DIRECT",
            "apd-pcdnwxlogin.teg.tencent-cloud.net": "DIRECT",
            "api.deepseek.com": "DIRECT",
            "deepseeksvc.com": "DIRECT",
            "api.moonshot.ai": "DIRECT",
            "api.bigmodel.cn": "DIRECT",
            "qwenlm.ai": "DIRECT",
            "coze.cn": "DIRECT",
            "coze.com": AI,
            "trae-api-sg.mchost.guru": AI,
            "abtestvm-sg.bytedance.com": AI,
            "claude.ai": AI,
            "anthropic.auth0.com": AI,
            "chatgpt.com": AI,
            "api.openai.com": AI,
            "gemini.google.com": AI,
            "generativelanguage.googleapis.com": AI,
            "accounts.google.com": AI,
            "challenges.cloudflare.com": NODE,
            "www.recaptcha.net": NODE,
            "api.cloudflare.com": NODE,
            "d1.awsstatic.com": NODE,
            "browser-intake-datadoghq.com": NODE,
            "copilot.microsoft.com": AI,
            "redirector.gvt1.com": NODE,
            "beacons.gvt2.com": NODE,
            "storage.googleapis.com": NODE,
            "play.googleapis.com": NODE,
            "stun.l.google.com": NODE,
            "stun.cloudflare.com": NODE,
            "unrelated.auth0.com": NODE,
            "dl.google.com": "DIRECT",
            "www.youtube.com": MEDIA,
            "rr1.googlevideo.com": MEDIA,
            "www.netflix.com": MEDIA,
            "tiktokrow-cdn.com": MEDIA,
            "api.tiktok.com": MEDIA,
            "api.snssdk.com": "DIRECT",
            "www.douyin.com": "DIRECT",
            "www.reddit.com": SOCIAL,
            "api.telegram.org": TELEGRAM,
            "unmatched.example": FALLBACK,
        }
        for domain, expected in cases.items():
            with self.subTest(domain=domain):
                self.assertEqual(first_match(self.expanded, domain), expected)

    def test_domestic_process_precedes_public_stun(self):
        for process in ("WeChat.exe", "Weixin", "com.tencent.mm", "com.taobao.taobao"):
            with self.subTest(process=process):
                self.assertEqual(first_match(self.expanded, "stun.l.google.com", process), "DIRECT")

    def test_tiktok_process_precedes_shared_domestic_domain(self):
        self.assertEqual(first_match(self.expanded, "api.snssdk.com", "com.zhiliaoapp.musically"), MEDIA)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--generated-yaml", type=Path)
    options, remaining = parser.parse_known_args()
    ONLINE = options.online
    CACHE_DIR = options.cache_dir
    GENERATED_YAML = options.generated_yaml
    unittest.main(argv=[sys.argv[0], *remaining])
