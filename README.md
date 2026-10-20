# Clash Rules for Mainland China

`acl4ssr-ai-chain-v2.ini` is a subconverter external configuration, not a
standalone Clash/Mihomo YAML file. Supply it as the converter's `config`
parameter together with your subscription. A working proxy subscription is
still required.

## Routing Defaults

- Known domestic applications, domestic AI services and domestic download CDNs
  use DIRECT. Steam's location-detection and download hosts are also DIRECT and
  stay that way when the game group is switched to a node (see below).
- Overseas AI, social, streaming and game services use their respective groups.
- OpenAI traffic is pinned inline to AI immediately after the LAN rules and
  before domestic process overrides. ChatGPT, Codex, API, authentication, file
  transfers, updates, documentation, status and WebSocket subdomains are covered
  independently of the aggregated AI list. The canonical source is
  [`rules/openai-ai.list`](rules/openai-ai.list); its active rules must remain
  identical to the marked block in the INI so remote conversions are self-contained.
  This includes all dependencies in OpenAI's
  [official network recommendations](https://help.openai.com/en/articles/9247338-network-recommendations-for-chatgpt-errors-on-web-and-apps),
  checked on 2026-10-16. Shared dependencies such as Cloudflare challenges,
  Intercom, SendGrid tracking, and the listed WorkOS, Stripe and telemetry hosts
  also use AI when requested by other sites: domain routing cannot identify the
  originating website. Other Stripe/Sentry tenants retain node selection.
  No public-cloud ASN or whole Codex/browser process is pinned to AI; commands
  and third-party integrations still follow their destination rules.
- ChatGPT Voice's 23 currently published IP ranges are pinned to AI with
  `no-resolve`, before process fallbacks. They come from the
  [official voice JSON](https://openai.com/chatgpt-voice.json), retrieved on
  2026-10-16 (source creation time: 2026-03-26). Refresh both the canonical list
  and its inline block when the online check reports a new range. UDP voice
  requires transparent/TUN capture and a UDP-capable AI exit.
- Anthropic traffic is pinned to the AI group: claude.ai, claude.com and the
  other Claude product domains, anthropic.com with all its subdomains
  (API, console, statsig telemetry), plus dedicated third-party hostnames such
  as anthropic.auth0.com and anthropic.com.cdn.cloudflare.net are matched
  inline before shared SaaS fallbacks and the aggregated AI list. Upstream list
  changes cannot move Anthropic traffic out of the AI group. Multi-tenant
  telemetry domains (other sentry.io ingest and datadog hosts) stay on node
  selection by design; Cloudflare challenges and the OpenAI dependency exceptions
  above use AI. Align the AI and node-selection exits if login challenges loop.
- Microsoft and Apple groups default to DIRECT, but can be switched to a proxy.
- Games and unmatched traffic default to node selection. DIRECT remains an
  explicit option.
- Steam's location detection and content downloads stay DIRECT even when the
  game group is switched to a node; everything else about the game group still
  follows it. At startup Steam fetches
  `http://ipv6check-http.steamserver.net/` and reports the external address it
  sees, and it discovers CMs through `steamserver.net`; when those followed a
  node, the reported address was the node's and Steam re-regionized to it. Both
  are pinned DIRECT inline before every Steam list and the generic direct rules,
  together with `cm.steampowered.com` and the download hosts:
  `steamcontent.com` (including `cache*-<region>.steamcontent.com`),
  `content.steamchina.com`, `steamcontent.tnkjmec.com`, the mainland mirrors
  (`clngaa.com`, `ksyna.com`, `eccdnx.com`, `bscstorage.net`,
  `pinyuncloud.com`, `pphimalayanrt.com`, `wmsjsteam.com`, the two
  `8686c.com` Steam hosts) and the CDN redirect targets seen in client logs
  (`cyngaa.com`, `sycontroller.com`, `gdtstream.com`, `manlaxy.com`,
  `steam.nsclouds.cn`). Valve therefore sees the local ISP address, picks the
  nearest mainland region, and package bodies come from mainland mirrors over
  the local ISP exit instead of consuming the selected node's bandwidth.
  Overseas partner CDNs in the Steam list (`steampipe*.akamaized.net`,
  `hwcdn.net`) are deliberately left out so they keep following the game group.
  The canonical source is [`rules/steam-direct.list`](rules/steam-direct.list);
  its rules must stay identical to the marked block in the INI.
- `steamusercontent.com`, `steamchina.com` and Epic's download CDN
  `epicgames-download1.storage.googleapis.com` (otherwise claimed by Google
  list's `googleapis.com` suffix) are pinned inline to the game group ahead of
  every other match. Steam/Epic client processes (`steam.exe`,
  `steamwebhelper.exe`, `EpicGamesLauncher.exe`, …) fall back to the game group
  after all destination rules, catching IP-only connections that no domain rule
  can match; known destinations such as the Steam location and download hosts
  are matched first and keep their DIRECT exit. Process rules need local process
  identification; on a router the domain pins still apply.
- aria2 and FDM follow destination rules, just like a browser. Selected BT
  clients use DIRECT only after known destination rules have been checked.
- No advertising blocklist or unconditional unblocking allowlist is imported.

Existing clients can restore saved group selections. After updating, check the
game and unmatched-traffic groups: a previously saved DIRECT selection may
override the new defaults.

Overseas AI uses VPSDance's Quantumult X list because it excludes whole-process
rules. The `quanx:` prefix is required: subconverter must translate `HOST` rules
to Clash domain rules. Do not replace it with the Surge list, whose process rules
would also proxy domestic requests from Cursor, Codex and other AI clients.
OpenAI and Anthropic are additionally pinned inline ahead of that list, so their
explicit coverage does not depend on upstream changes; the aggregated list
supplements it. OpenAI's list avoids upstream's broad `openai` keyword, which
would also match unrelated domains containing that text.

## Optional Residential Proxies

The AI and social groups prefer the existing US/Austria residential node names
using anchored subscription-name filters. Missing nodes are skipped and the
groups fall back to node selection; no undefined proxy reference is emitted.
This template does not construct proxy chains.

Nodes or groups created later by a client override are not visible to
subconverter's filters. That override must both create the chain and add its
name to the relevant group's proxy list.

## Client Prerequisites

- Configure DNS in the client or converter base. Proxy routing alone does not
  prevent DNS pollution or force DNS requests through a proxy. Configure
  bootstrap/proxy-server DNS to avoid resolution loops.
- Configure TUN or another transparent mode when UDP and non-HTTP applications
  need coverage. System HTTP proxy settings alone do not capture all traffic.
- Cover IPv6 consistently in DNS and routing, or disable it consistently if
  the client/network cannot handle it.
- Process rules require local process identification. A router cannot identify
  processes on downstream devices; process-based TikTok and BT exceptions will
  not apply there.
- STUN rules require a UDP-capable proxy and do not replace browser WebRTC
  privacy settings.
- Keep session-sensitive services on a stable exit. Using load balancing can
  send related domains through different exits; use the same exit for AI
  sessions and shared authentication/challenge services when necessary.

## Verification

Run from the repository root:

```powershell
python -B -m unittest discover -s tests -v
python -B tests/test_rules.py --online -v
python -B tests/test_rules.py --generated-yaml path/to/converted.yaml -v
```

Online and generated-YAML checks require PyYAML. `--cache-dir PATH` saves fetched
rule sources for inspection. Tests cover rule order, destination/process routing,
default group choices, OpenAI dependency/process precedence, literal voice IP
routing, current official voice-range coverage (online), game-platform exit
handling (Steam location and download hosts pinned DIRECT ahead of the Steam
lists, store/community/UGC and Epic on the game group, Epic download CDN
precedence over the Google list, the client-process fallback), and generated
proxy references. Validate converted YAML
with your actual core too, for example `mihomo -t -f path/to/converted.yaml`.
These checks do not establish real network reachability or DNS/WebRTC privacy.
