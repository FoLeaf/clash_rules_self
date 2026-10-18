"""Run offline: python -B -m unittest discover -s tests -v

Check live sources too: python -B tests/test_rules.py --online -v
Online checks require PyYAML. --cache-dir stores downloaded source snapshots.
--generated-yaml checks domain routing in actual subconverter output instead.
These are domain/process checks, not DNS, IP-resolution, or connectivity tests.
"""

import argparse
import hashlib
import ipaddress
import json
import re
import sys
import time
import unittest
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "acl4ssr-ai-chain-v2.ini"
OVERRIDES = ROOT / "rules" / "cn-direct-override.list"
OPENAI_OVERRIDES = ROOT / "rules" / "openai-ai.list"
# Independent acceptance cases from OpenAI's published network recommendations,
# plus product endpoints and dedicated CDN/voice hosts. Do not derive from rules.
OPENAI_DOMAINS = (
    "openai.com", "api.openai.com", "platform.openai.com", "developers.openai.com",
    "auth.openai.com", "auth0.openai.com", "setup.auth.openai.com",
    "chat.openai.com", "desktop.chat.openai.com", "android.chat.openai.com",
    "ios.chat.openai.com", "tcr9i.chat.openai.com", "cdn.platform.openai.com",
    "chatgpt.com", "ws.chatgpt.com", "chatgpt.com.", "CHATGPT.COM",
    "ab.chatgpt.com", "codex-cloud-environments.chatgpt.com",
    "sora.chatgpt.com", "sora.com", "chat.com", "status.openai.com",
    "cdn.oaistatic.com", "files.oaiusercontent.com", "ab.oaistatsig.com",
    "cdn.openaimerge.com", "ab.ct.sendgrid.net", "api.intercom.io",
    "js.intercomcdn.com", "cdn.workos.com", "forwarder.workos.com",
    "frontend-apps-multi-region.workos.com", "setup.workos.com",
    "images.workoscdn.com", "workos.imgix.net", "challenges.cloudflare.com",
    "humb.apple.com", "js.stripe.com", "o207216.ingest.sentry.io",
    "o33249.ingest.sentry.io", "rum.browser-intake-datadoghq.com",
    "chat.openai.com.cdn.cloudflare.net", "openaiapi-site.azureedge.net",
    "openaicom.imgix.net", "openai-api.arkoselabs.com",
    "openaiassets.blob.core.windows.net",
    "openaicom-api-bdcpf8c6d2e9atf6.z01.azurefd.net",
    "openaicomproductionae4b.blob.core.windows.net",
    "production-openaicom-storage.azureedge.net", "chatgpt.livekit.cloud",
    "region.chatgpt.livekit.cloud", "region.host.livekit.cloud",
    "region.turn.livekit.cloud", "api.statsig.com", "events.statsigapi.net",
    "featuregates.org", "client-api.arkoselabs.com",
)
NODE = "\U0001f680 \u8282\u70b9\u9009\u62e9"
AI = "\U0001f916 AI"
MEDIA = "\U0001f3ac \u56fd\u5916\u6d41\u5a92\u4f53"
SOCIAL = "\U0001f310 \u56fd\u5916\u793e\u4ea4"
TELEGRAM = "\U0001f4f2 \u7535\u62a5\u6d88\u606f"
FALLBACK = "\U0001f41f \u6f0f\u7f51\u4e4b\u9c7c"
GAMES = "\U0001f3ae \u6e38\u620f\u5e73\u53f0"
APPLE = "\U0001f34e \u82f9\u679c\u670d\u52a1"
MICROSOFT = "\u24c2\ufe0f \u5fae\u8f6f\u670d\u52a1"
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
    for kind in ("surge", "quanx", "clash-domain", "clash-ipcidr", "clash-classic"):
        if source.startswith(kind + ":"):
            return kind, source[len(kind) + 1:]
    return "surge", source


def parse_ruleset(text, kind):
    if kind.startswith("clash-"):
        import yaml

        payload = yaml.load(text, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))["payload"]
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
        return entries

    entries = active_lines(text)
    if kind == "quanx":
        aliases = {
            "HOST": "DOMAIN",
            "HOST-SUFFIX": "DOMAIN-SUFFIX",
            "HOST-KEYWORD": "DOMAIN-KEYWORD",
            "IP6-CIDR": "IP-CIDR6",
        }
        normalized = []
        for entry in entries:
            parts = [part.strip() for part in entry.split(",")]
            if len(parts) < 2 or not parts[1]:
                raise ValueError("Expected a Quantumult X rule with a payload")
            rule_type = parts[0].upper()
            rule = aliases.get(rule_type, rule_type) + "," + parts[1]
            # The INI target replaces any Quantumult X policy tag.
            if len(parts) > 2 and parts[-1] == "no-resolve":
                rule += ",no-resolve"
            normalized.append(rule)
        entries = normalized
    if not entries or any(not re.match(r"^[A-Z][A-Z0-9-]*,", entry) for entry in entries):
        raise ValueError("Expected a plain rule list, not YAML or HTML")
    return entries


def select_members(group, nodes):
    name, kind, *selectors = group.split("`")
    if kind != "select":
        raise ValueError(f"{name} is not a select group")
    members = []
    for selector in selectors:
        if selector.startswith("[]"):
            members.append(selector[2:])
        else:
            members.extend(node for node in nodes if node not in members and re.search(selector, node))
    return members or ["DIRECT"]


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


def first_match(rules, domain, process=None, destination_ip=None):
    domain = domain.lower().rstrip(".")
    address = ipaddress.ip_address(destination_ip) if destination_ip else None
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
        if kind in ("IP-CIDR", "IP-CIDR6") and address:
            if address in ipaddress.ip_network(value, strict=False):
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
        group_values = values(self.text, "custom_proxy_group")
        groups = [value.split("`")[0] for value in group_values]
        self.assertEqual(len(groups), len(set(groups)))
        for target, _ in self.rules:
            self.assertIn(target, [*groups, "DIRECT", "REJECT"])
        for group in group_values:
            for member in group.split("`")[2:]:
                if member.startswith("[]"):
                    self.assertIn(member[2:], [*groups, "DIRECT", "REJECT"], group)
        self.assertEqual(len(self.rules), len(set(self.rules)))

    def test_select_defaults_and_optional_residential_nodes(self):
        groups = {group.split("`")[0]: group for group in values(self.text, "custom_proxy_group")}
        ordinary_nodes = ["Example SG", "Example US"]
        for name in (AI, SOCIAL, GAMES, FALLBACK):
            self.assertEqual(select_members(groups[name], ordinary_nodes)[0], NODE, name)
        for name in (APPLE, MICROSOFT):
            self.assertEqual(select_members(groups[name], ordinary_nodes)[0], "DIRECT", name)
        for name in (AI, SOCIAL):
            selectors = groups[name].split("`")[2:4]
            for selector in selectors:
                self.assertTrue(selector.startswith("^") and selector.endswith("$"), selector)
            preferred, alternate = [selector[1:-1] for selector in selectors]
            nodes = [*ordinary_nodes, alternate, preferred]
            self.assertEqual(select_members(groups[name], nodes)[:2], [preferred, alternate])
            self.assertEqual(select_members(groups[name], [alternate, *ordinary_nodes])[0], alternate)

    def test_override_file_is_inlined_in_order(self):
        block = self.text.split("; BEGIN CN DIRECT OVERRIDES\n", 1)[1]
        block = block.split("; END CN DIRECT OVERRIDES", 1)[0]
        expected = [("DIRECT", "[]" + rule) for rule in active_lines(OVERRIDES.read_text(encoding="utf-8-sig"))]
        self.assertEqual(rulesets(block), expected)
        for _, source in expected:
            self.assertRegex(source, r"^\[\](PROCESS-NAME|DOMAIN|DOMAIN-SUFFIX),[^,]+$")

    def test_openai_overrides_are_inlined_before_process_and_shared_rules(self):
        block = self.text.split("; BEGIN OPENAI AI OVERRIDES\n", 1)[1]
        block = block.split("; END OPENAI AI OVERRIDES", 1)[0]
        expected = [(AI, "[]" + rule) for rule in active_lines(
            OPENAI_OVERRIDES.read_text(encoding="utf-8-sig"))]
        self.assertEqual(rulesets(block), expected)
        end = max(self.rules.index(rule) for rule in expected)
        for index, (_, source) in enumerate(self.rules):
            if "PROCESS-NAME," in source or source.endswith((
                    ",auth0.com", ",sentry", ",stripe.com", "/global.list",
                    "/Apple.list", "/ChinaDomain.list")):
                self.assertLess(end, index, source)
        for _, source in expected:
            self.assertRegex(source, r"^\[\](DOMAIN|DOMAIN-SUFFIX|IP-CIDR6?),")
        self.assertFalse(any(policy == AI and "PROCESS-" in source
                             for policy, source in self.rules))

    def test_openai_domains_do_not_depend_on_remote_lists_or_process(self):
        for domain in OPENAI_DOMAINS:
            for process in (None, "Codex.exe", "codex", "ChatGPT.exe", "chrome.exe",
                            "WeChat.exe", "com.android.vending", "qbittorrent.exe"):
                with self.subTest(domain=domain, process=process):
                    self.assertEqual(first_match(self.inline, domain, process), AI)

    def test_openai_does_not_capture_unrelated_cloud_tenants(self):
        for domain, expected in {
            "unrelated.auth0.com": NODE, "api.stripe.com": NODE,
            "unrelated.ingest.sentry.io": NODE,
            "browser-intake-datadoghq.com": NODE,
            "unrelated.blob.core.windows.net": FALLBACK,
            "unrelated.azureedge.net": FALLBACK,
            "unrelated.workos.com": FALLBACK,
            "openai.com.example.org": FALLBACK,
            "fakeopenai.com": FALLBACK,
        }.items():
            with self.subTest(domain=domain):
                self.assertEqual(first_match(self.inline, domain), expected)

    def test_voice_literal_ips_precede_process_fallbacks(self):
        networks = [rule for rule in active_lines(OPENAI_OVERRIDES.read_text(encoding="utf-8"))
                    if rule.startswith(("IP-CIDR,", "IP-CIDR6,"))]
        self.assertTrue(networks)
        for rule in networks:
            self.assertTrue(rule.endswith(",no-resolve"), rule)
            address = str(ipaddress.ip_network(rule.split(",")[1]).network_address)
            with self.subTest(address=address):
                self.assertEqual(first_match(self.inline, "", "WeChat.exe", address), AI)
        self.assertEqual(first_match(self.inline, "", destination_ip="192.0.2.1"), FALLBACK)

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
        for suffix in (",gvt1.com", ",gvt2.com", ",gvt3.com", ",storage.googleapis.com",
                       ",googleapis.cn", ",xn--ngstr-lra8j.com", ",linux.sb",
                       "/global.list", "/YouTube.list", "/TikTok.list",
                       "/Bing.list", "/OneDrive.list", "/Microsoft.list", "/Apple.list",
                       "/Epic.list", "/Steam.list", "/Nintendo.list", "/PlayStation.list"):
            self.assertLess(self.position(suffix), min(direct, china), suffix)
        self.assertLess(self.position("/global.list"), self.position("/cn.list"))
        self.assertNotIn("/rules/surge/all.list", self.text)

    def test_ai_source_excludes_whole_process_routing(self):
        source = self.rules[self.position("/global.list")][1]
        kind, url = source_type(source)
        self.assertEqual(kind, "quanx")
        self.assertEqual(url, "https://raw.githubusercontent.com/VPSDance/ai-proxy-rules/main/rules/quantumult-x/global.list")

    def test_downloads_follow_destination_before_bt_fallback(self):
        self.assertFalse(any(source.endswith(("/UnBan.list", "/Download.list")) for _, source in self.rules))
        self.assertLess(self.position("/SteamCN.list"), self.position("/Steam.list"))
        for process in ("qbittorrent.exe", "qbittorrent", "Transmission.exe", "Transmission",
                        "transmission-daemon", "uTorrent.exe", "WebTorrent.exe", "WebTorrent Helper.exe"):
            position = self.position("[]PROCESS-NAME," + process)
            self.assertGreater(position, self.position("/gfw.txt"))
            self.assertLess(position, self.position("/ChinaCompanyIp.list"))

    def test_google_and_ip_fallback_order(self):
        for suffix in ("/global.list", "/YouTube.list", "/GoogleCN.list"):
            self.assertLess(self.position(suffix), self.position("/Google.list"))
        for suffix in ("/ChinaCompanyIp.list", "/cncidr.txt", "[]GEOIP,CN,no-resolve"):
            self.assertLess(self.position("/gfw.txt"), self.position(suffix))
        self.assertEqual(self.rules[-1], (FALLBACK, "[]FINAL"))
        self.assertEqual(sum(source in ("[]FINAL", "[]MATCH") for _, source in self.rules), 1)
        fallback = next(group for group in values(self.text, "custom_proxy_group") if group.startswith(FALLBACK + "`"))
        self.assertEqual(fallback.split("`")[2], "[]" + NODE)

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
            "linux.sb": NODE,
            "www.linux.sb": NODE,
            "redirector.gvt1.com": NODE,
            "services.googleapis.cn": NODE,
            "r3---sn-ni5e6n7z.xn--ngstr-lra8j.com": NODE,
            "android.googleapis.com": NODE,
            "storage.googleapis.com": NODE,
            "stun.l.google.com": NODE,
            "stun.cloudflare.com": NODE,
            "global.stun.twilio.com": NODE,
            "claude.ai": AI,
            "www.claude.com": AI,
            "api.anthropic.com": AI,
            "console.anthropic.com": AI,
            "statsig.anthropic.com": AI,
            "code.claude.dev": AI,
            "claudeusercontent.com": AI,
            "claudemcpcontent.com": AI,
            "anthropic.com.cdn.cloudflare.net": AI,
            "servd-anthropic-website.b-cdn.net": AI,
            "anthropic-com.ghost.io": AI,
            "anthropic.auth0.com": AI,
            "challenges.cloudflare.com": AI,
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
        self.assertEqual(first_match(self.inline, "unmatched.example", "com.android.vending"), NODE)

    def test_anthropic_traffic_is_locked_to_ai_group(self):
        block = self.position("[]DOMAIN-SUFFIX,anthropic.com")
        for guard in ("[]DOMAIN-SUFFIX,auth0.com", "[]DOMAIN-KEYWORD,sentry",
                      "/global.list", "/Google.list", "/ChinaDomain.list", "[]FINAL"):
            self.assertLess(block, self.position(guard), guard)
        anthropic_rules = [(policy, rule) for policy, rule in self.inline
                           if "anthropic" in rule or "claude" in rule]
        self.assertEqual(len(anthropic_rules), 14)
        for policy, rule in anthropic_rules:
            self.assertEqual(policy, AI, rule)
        for domain in ("claude.ai", "claude.com", "anthropic.com", "claudeusercontent.com",
                       "api.anthropic.com", "statsig.anthropic.com"):
            with self.subTest(domain=domain):
                self.assertEqual(first_match(self.inline, domain), AI)

    def test_game_platform_traffic_is_locked_to_game_group(self):
        # Region detection, CM and download CDNs must all leave through the game
        # group so its selection fully decides which IP Steam/Epic can observe.
        for domain in ("steamserver.net", "cm.steampowered.com", "cache1-hkg1.steamserver.net",
                       "steamcontent.com", "steamusercontent.com", "steamchina.com",
                       "epicgames-download1.storage.googleapis.com"):
            with self.subTest(domain=domain):
                self.assertEqual(first_match(self.inline, domain), GAMES)
        block = self.position("[]DOMAIN-SUFFIX,steamserver.net")
        for guard in ("/Google.list", "/gfw.txt", "/ChinaDomain.list", "/direct.txt", "[]FINAL"):
            self.assertLess(block, self.position(guard), guard)
        # The Epic download CDN must be claimed before Google.list's googleapis.com suffix.
        self.assertLess(self.position("[]DOMAIN,epicgames-download1.storage.googleapis.com"),
                        self.position("/Google.list"))
        # Steam CN domains stay ahead of the main Steam list, now with the same target.
        self.assertLess(self.position("/SteamCN.list"), self.position("/Steam.list"))
        self.assertEqual(self.rules[self.position("/SteamCN.list")][0], GAMES)

    def test_game_process_fallback_follows_game_group(self):
        # IP-only CM/Download connections carry no domain; the process fallback is
        # the only rule that can keep them on the game group's selected exit.
        for process in ("steam.exe", "steamwebhelper.exe", "steam", "steamwebhelper",
                        "EpicGamesLauncher.exe", "EpicWebHelper.exe"):
            with self.subTest(process=process):
                self.assertEqual(first_match(self.inline, "unmatched.example", process), GAMES)
                self.assertEqual(first_match(self.inline, "", process, "203.0.113.8"), GAMES)
        # Known destinations still follow their own rules instead of the game group.
        self.assertEqual(first_match(self.inline, "api.openai.com", "steam.exe"), AI)
        self.assertEqual(first_match(self.inline, "api.anthropic.com", "steamwebhelper.exe"), AI)
        self.assertEqual(first_match(self.inline, "wechat.com", "steam.exe"), "DIRECT")
        # The fallback runs only after domain rules, like the BT client fallback.
        position = self.position("[]PROCESS-NAME,steam.exe")
        self.assertGreater(position, self.position("/gfw.txt"))
        self.assertLess(position, self.position("/ChinaCompanyIp.list"))
        for process in ("aria2c.exe", "fdm.exe", "chrome.exe", "Codex.exe"):
            self.assertNotEqual(first_match(self.inline, "unmatched.example", process), GAMES)


class RulesetParsingTests(unittest.TestCase):
    def test_quanx_prefix(self):
        self.assertEqual(source_type("quanx:https://example.com/global.list"),
                         ("quanx", "https://example.com/global.list"))

    def test_quanx_rules_are_normalized(self):
        text = "\n".join((
            "# comment",
            "HOST,api.example.com",
            "HOST-SUFFIX,example.com,old-policy",
            "host-keyword,example,old-policy",
            "IP-CIDR,192.0.2.0/24,no-resolve",
            "IP6-CIDR,2001:db8::/32,old-policy,no-resolve",
        ))
        self.assertEqual(parse_ruleset(text, "quanx"), [
            "DOMAIN,api.example.com",
            "DOMAIN-SUFFIX,example.com",
            "DOMAIN-KEYWORD,example",
            "IP-CIDR,192.0.2.0/24,no-resolve",
            "IP-CIDR6,2001:db8::/32,no-resolve",
        ])

    def test_invalid_lists_fail(self):
        for kind in ("surge", "quanx"):
            for text in ("", "# empty", "<html>error</html>", "payload:\n  - '+.example.com'"):
                with self.subTest(kind=kind, text=text):
                    with self.assertRaises(ValueError):
                        parse_ruleset(text, kind)


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
                entries = parse_ruleset(text, kind)
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
            "claude.com": AI,
            "api.anthropic.com": AI,
            "statsig.anthropic.com": AI,
            "claudeusercontent.com": AI,
            "code.claude.dev": AI,
            "anthropic.com.cdn.cloudflare.net": AI,
            "anthropic.auth0.com": AI,
            "chatgpt.com": AI,
            "api.openai.com": AI,
            "gemini.google.com": AI,
            "generativelanguage.googleapis.com": AI,
            "accounts.google.com": AI,
            "challenges.cloudflare.com": AI,
            "www.recaptcha.net": NODE,
            "api.cloudflare.com": NODE,
            "d1.awsstatic.com": NODE,
            "browser-intake-datadoghq.com": NODE,
            "copilot.microsoft.com": AI,
            "linux.sb": NODE,
            "www.linux.sb": NODE,
            "redirector.gvt1.com": NODE,
            "beacons.gvt2.com": NODE,
            "r3---sn-ni5e6n7z.xn--ngstr-lra8j.com": NODE,
            "services.googleapis.cn": NODE,
            "android.googleapis.com": NODE,
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

    def test_openai_domains_in_expanded_rules(self):
        for domain in OPENAI_DOMAINS:
            for process in (None, "Codex.exe", "WeChat.exe", "com.android.vending"):
                with self.subTest(domain=domain, process=process):
                    self.assertEqual(first_match(self.expanded, domain, process), AI)

    def test_current_official_voice_ranges(self):
        if not ONLINE:
            self.skipTest("Use --online to compare with the current official voice JSON")
        data = json.loads(fetch_text("https://openai.com/chatgpt-voice.json"))
        self.assertTrue(data["prefixes"])
        networks = [ipaddress.ip_network(rule.split(",")[1])
                    for policy, rule in self.expanded
                    if policy == AI and rule.startswith(("IP-CIDR,", "IP-CIDR6,"))]
        for prefix in data["prefixes"]:
            network = ipaddress.ip_network(prefix.get("ipv4Prefix") or prefix["ipv6Prefix"])
            with self.subTest(network=str(network)):
                self.assertTrue(any(network.version == item.version and network.subnet_of(item)
                                    for item in networks), "Refresh OpenAI voice IP rules")
                self.assertEqual(first_match(self.expanded, "", "WeChat.exe",
                                             str(network.network_address)), AI)

    def test_domestic_process_precedes_public_stun(self):
        for process in ("WeChat.exe", "Weixin", "com.tencent.mm", "com.taobao.taobao"):
            with self.subTest(process=process):
                self.assertEqual(first_match(self.expanded, "stun.l.google.com", process), "DIRECT")

    def test_tiktok_process_precedes_shared_domestic_domain(self):
        self.assertEqual(first_match(self.expanded, "api.snssdk.com", "com.zhiliaoapp.musically"), MEDIA)

    def test_play_store_process_uses_node(self):
        self.assertEqual(first_match(self.expanded, "unmatched.example", "com.android.vending"), NODE)

    def test_service_groups_are_selectable(self):
        cases = {
            "steamcommunity.com": GAMES,
            "store.steampowered.com": GAMES,
            "login.epicgames.com": GAMES,
            "account-public-service-prod03.ol.epicgames.com": GAMES,
            "www.playstation.com": GAMES,
            "accounts.nintendo.com": GAMES,
            "music.apple.com": APPLE,
            "www.apple.com": APPLE,
            "apps.apple.com": APPLE,
            "www.icloud.com": APPLE,
            "cn.bing.com": MICROSOFT,
            "onedrive.live.com": MICROSOFT,
        }
        for domain, expected in cases.items():
            with self.subTest(domain=domain):
                self.assertEqual(first_match(self.expanded, domain), expected)

    def test_game_platform_region_and_download_domains_follow_game_group(self):
        # Steam region detection (CM), the Epic download CDN under googleapis.com
        # and the CN content CDNs must leave through the game group, not through
        # node selection or a hardcoded DIRECT.
        cases = {
            "cm.steampowered.com": GAMES,
            "cache1-hkg1.steamserver.net": GAMES,
            "clientconfig.akam.steamstatic.com": GAMES,
            "epicgames-download1.storage.googleapis.com": GAMES,
            "dl.steam.clngaa.com": GAMES,
            "cdn.steamcontent.com": GAMES,
        }
        for domain, expected in cases.items():
            with self.subTest(domain=domain):
                self.assertEqual(first_match(self.expanded, domain), expected)

    def test_domestic_downloads_stay_direct(self):
        for domain in ("dl.google.com", "www.bilibili.com"):
            with self.subTest(domain=domain):
                self.assertEqual(first_match(self.expanded, domain), "DIRECT")

    def test_general_downloaders_follow_destination(self):
        cases = {
            "drive.google.com": NODE,
            "raw.githubusercontent.com": NODE,
            "archive.org": NODE,
            "steamcommunity.com": GAMES,
            "dl.steam.clngaa.com": GAMES,
            "www.baidu.com": "DIRECT",
            "unmatched.example": FALLBACK,
        }
        for process in (None, "aria2c.exe", "fdm.exe"):
            for domain, expected in cases.items():
                with self.subTest(process=process, domain=domain):
                    self.assertEqual(first_match(self.expanded, domain, process), expected)

    def test_ai_clients_follow_destination(self):
        cases = {
            "api.siliconflow.cn": "DIRECT",
            "api.moonshot.ai": "DIRECT",
            "api.deepseek.com": "DIRECT",
            "www.baidu.com": "DIRECT",
            "pypi.tuna.tsinghua.edu.cn": "DIRECT",
            "api.openai.com": AI,
            "claude.ai": AI,
            "api.anthropic.com": AI,
            "generativelanguage.googleapis.com": AI,
            "trae-api-sg.mchost.guru": AI,
            "abtestvm-sg.bytedance.com": AI,
            "drive.google.com": NODE,
            "unmatched.example": FALLBACK,
        }
        for process in ("Cursor.exe", "Codex.exe", "Claude.exe", "Windsurf", "Antigravity.exe"):
            for domain, expected in cases.items():
                with self.subTest(process=process, domain=domain):
                    self.assertEqual(first_match(self.expanded, domain, process), expected)
        self.assertFalse(any(policy == AI and rule.startswith(("PROCESS-", "PACKAGE-NAME,"))
                             for policy, rule in self.expanded))

    def test_bt_direct_is_only_a_fallback(self):
        for process in ("qbittorrent.exe", "Transmission", "transmission-daemon", "uTorrent.exe"):
            with self.subTest(process=process):
                self.assertEqual(first_match(self.expanded, "unmatched.example", process), "DIRECT")
                self.assertEqual(first_match(self.expanded, "raw.githubusercontent.com", process), NODE)


class GeneratedConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GENERATED_YAML:
            raise unittest.SkipTest("Use --generated-yaml for actual converter group checks")
        import yaml

        cls.config = yaml.load(GENERATED_YAML.read_text(encoding="utf-8-sig"),
                               Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))

    def test_all_references_exist(self):
        groups = self.config["proxy-groups"]
        names = [proxy["name"] for proxy in self.config["proxies"]] + [group["name"] for group in groups]
        self.assertEqual(len(names), len(set(names)))
        available = {*names, "DIRECT", "REJECT"}
        for group in groups:
            self.assertTrue(group["proxies"], group["name"])
            for member in group["proxies"]:
                self.assertIn(member, available, group["name"])
        for rule in self.config["rules"]:
            parts = rule.split(",")
            self.assertNotIn(parts[0], ("HOST", "HOST-SUFFIX", "HOST-KEYWORD", "IP6-CIDR", "RULE-SET"))
            target = parts[1] if parts[0] in ("FINAL", "MATCH") else parts[2]
            self.assertIn(target, available, rule)

    def test_select_groups_match_template(self):
        nodes = [proxy["name"] for proxy in self.config["proxies"]]
        generated = {group["name"]: group for group in self.config["proxy-groups"]}
        for group in values(CONFIG.read_text(encoding="utf-8-sig"), "custom_proxy_group"):
            name, kind, *_ = group.split("`")
            if kind == "select":
                self.assertEqual(generated[name]["proxies"], select_members(group, nodes), name)

    def test_openai_voice_no_resolve_is_preserved(self):
        for rule in active_lines(OPENAI_OVERRIDES.read_text(encoding="utf-8")):
            if rule.startswith(("IP-CIDR,", "IP-CIDR6,")):
                kind, network, flag = rule.split(",")
                self.assertIn(f"{kind},{network},{AI},{flag}", self.config["rules"])


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
