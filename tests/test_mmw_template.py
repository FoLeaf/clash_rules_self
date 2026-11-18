"""Offline checks for the miaomiaowu template (`my_clash.yaml`).

mmw parses its rule-template slot as YAML. Feeding it the ACL4SSR INI fails with
``yaml: line 5: mapping values are not allowed in this context``; mmw then
silently serves the previous subscription file, so the client keeps stale rules
while the backend logs look harmless. ``my_clash.yaml`` is the compiled artifact
and must stay in sync with the INI.
"""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INI = ROOT / "acl4ssr-ai-chain-v2.ini"
TEMPLATE = ROOT / "my_clash.yaml"
BUILDER = ROOT / "tools" / "build_mmw_template.py"

_spec = importlib.util.spec_from_file_location("build_mmw_template", BUILDER)
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)


def bare(line):
    """Drop the YAML list marker so INI-compiled and template rules compare."""
    line = line.strip()
    return line[2:].strip() if line.startswith("- ") else line


class MmwTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = TEMPLATE.read_text(encoding="utf-8-sig")
        block = cls.text.split("\nrules:\n", 1)[1].split("\nrule-providers:\n", 1)[0]
        cls.rules = [bare(line) for line in block.splitlines() if line.strip()]
        cls.tags = {url: tag for tag, url in builder.provider_urls(cls.text).items()}

    def test_matches_the_ini(self):
        # The published template is generated, never hand-edited: rebuild from the
        # INI and compare, so an INI change cannot leave the template behind.
        rulesets = builder.ini_rulesets(INI.read_text(encoding="utf-8-sig"))
        compiled, missing = builder.compile_rules(rulesets, self.tags)
        self.assertEqual(missing, [])
        self.assertEqual([bare(line) for line in compiled], self.rules)

    def test_no_node_credentials(self):
        # mmw injects nodes from its own table (a template carrying three nodes
        # still renders four), so the published copy keeps an empty proxies list.
        block = self.text.split("\nproxies:", 1)[1].split("\nproxy-groups:", 1)[0]
        self.assertEqual(block.strip(), "[]")
        for marker in ("password:", "uuid:", "hysteria2", "vless", "trojan"):
            self.assertNotIn(marker, self.text)

    def test_rule_set_tags_resolve(self):
        used = {rule.split(",")[1] for rule in self.rules if rule.startswith("RULE-SET,")}
        self.assertTrue(used)
        self.assertEqual(used - set(builder.provider_urls(self.text)), set())

    def test_google_and_mediav_order(self):
        position = {rule: index for index, rule in enumerate(self.rules)}
        self.assertLess(position["DOMAIN-SUFFIX,mediav.com,REJECT"],
                        position["DOMAIN-SUFFIX,openai.com,🤖 AI"])
        epic = position["DOMAIN,epicgames-download1.storage.googleapis.com,🎮 游戏平台"]
        self.assertLess(epic, position["DOMAIN-SUFFIX,googleapis.com,🚀 节点选择"])
        for suffix in ("google.com", "gstatic.com", "googleapis.com"):
            self.assertIn(f"DOMAIN-SUFFIX,{suffix},🚀 节点选择", position)
        self.assertEqual(self.rules[-2:], ["MATCH,🐟 漏网之鱼", "MATCH,REJECT"])


if __name__ == "__main__":
    unittest.main()
