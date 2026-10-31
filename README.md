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
  inline before domestic process overrides, shared SaaS fallbacks and the
  aggregated AI list. Embedded browsers therefore use AI for these destinations
  even inside an otherwise DIRECT domestic application. Upstream list
  changes cannot move Anthropic traffic out of the AI group. Multi-tenant
  telemetry domains (other sentry.io ingest and datadog hosts) stay on node
  selection by design; Cloudflare challenges and the OpenAI dependency exceptions
  above use AI. Align the AI and node-selection exits if login challenges loop.
- Pinned AI domains get a QUIC fallback immediately after the Anthropic block:
  `AND((NETWORK,UDP),(DST-PORT,443),(DOMAIN…))` rules REJECT UDP 443 for the same
  domain set. On 2026-10-31 Mihomo logs showed claude.ai TCP exiting through
  `🤖 AI[🇺🇸 US-PPFLIGHT]` (US exit) while Firefox HTTP/3 traffic
  (`claude.com:443` UDP) matched no usable rule and fell through to DIRECT, so the
  page still loaded from the Chinese IP and Anthropic redirected to
  `app-unavailable-in-region`. The reject forces browsers back to TCP, which the AI
  rules already proxy; when the selected AI node supports UDP, QUIC is proxied and
  the reject never triggers. Logic rules need a Mihomo (meta) core.
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

## Google Fonts Direct-Path Observation

The upstream `GoogleCN.list` includes `fonts.googleapis.com` and
`fonts.gstatic.com`, and this template routes the full list to `DIRECT` before
the general Google list. On 2026-10-28, Mihomo repeatedly logged
`fonts.googleapis.com:443` matching `RuleSet/googlecn_27` and dialing `DIRECT`;
IPv4 attempts to Google addresses such as `172.217.75.95`, `142.251.41.10`,
and `142.251.215.170` timed out. IPv6 attempts failed because the address was
not valid in the local network context. A fresh PC-side curl through the local
Mihomo proxy returned HTTP 000 after about five seconds for Fonts, while the
same core returned HTTP 200 for `www.baidu.com` in about 0.1 seconds; Mihomo
logged both as `DIRECT` (`googlecn_27` and `chinadomain_40`, respectively).
The route policy is working; the Fonts host is being resolved to an address
that the PC cannot reach over its direct campus path.

During a Fonts request, the core's outbound TCP sockets used local address
`10.16.6.141`, which belongs to the physical Realtek `以太网 3` adapter, not
the Mihomo virtual adapter. That lowers the likelihood that TUN selected the
virtual adapter as its physical egress. The user reports a stronger same-
network comparison on the phone: with the phone connected to the same router
Wi-Fi, Fonts opens with Clash off, fails in Clash TUN mode using Rules/Direct,
and opens again with TUN off and system proxy mode on. On the PC, the user
initially reported that Rules-mode system-proxy mode opened Fonts, but a later
fresh Firefox private-window request returned 502. Its log showed
`127.0.0.1` ingress, `RuleSet/googlecn_27 → DIRECT`, and timeouts to
`142.251.215.74` and `142.251.214.106`; the initial success may have been
transient or served from the normal browser cache. Native curl with both TUN
and system proxy off timed out after five seconds. A second curl request
through the local mixed port `127.0.0.1:7890`, also with TUN and system proxy
off, was logged as
`DIRECT` via `RuleSet/googlecn_27` and timed out to `142.251.215.74:443`. Thus
the direct route through Mihomo fails outside TUN as well. The current PC
state has since returned to TUN on and system proxy off. Windows
Firewall profiles are currently
disabled. 360 Safe Guard Lite has several running kernel drivers, including
`360netmon`, although its UI process was not running; no matching Windows
event log or text log entry was found. A PC-specific security filter remains
possible. The phone's same-Wi-Fi TUN-only failure suggests a separate
TUN-specific issue may also exist there.

The PC receives `10.16.6.141/16` by DHCP from `10.16.0.1`, which is also its
default gateway. The user describes this as a home router operating on campus,
with one campus account and one public egress IP. The same-router phone test
shows that this shared path can serve Fonts outside TUN mode, so the campus
uplink is not a general block. With TUN and system proxy off, native queries
returned `120.253.253.97` from `223.5.5.5` and `120.253.250.225` from
`180.76.76.76`; Mihomo's direct attempts used `142.251.x.x`. This confirms
different DNS answer sets. Native curl and Mihomo DIRECT requests both timed
out on this PC when they used the Mihomo-observed addresses. A pinned-IP
comparison with TUN and system proxy off settled the distinction:
`curl --resolve` to `120.253.253.97` returned HTTP 200 in 0.227 seconds,
`120.253.250.225` returned HTTP 200 in 0.196 seconds, and
`142.251.215.74` timed out after 5.005 seconds. The browser hostname, TLS SNI,
and direct route were held constant. The failing behavior is therefore
address-set-dependent; the two system-DNS answers are reachable while the
Mihomo-observed Google address is not.

The PC's active DNS config has `ipv6: false`, `enhanced-mode: fake-ip`, and
`fake-ip-range: 198.18.0.1/16`; TUN DNS hijacking is configured. While TUN was
on, ordinary DNS lookup and explicit queries to the configured physical DNS
servers `223.5.5.5` and `180.76.76.76` returned fake address `198.18.0.18`, as
expected in fake-IP mode. Mihomo then resolved Fonts to real IPv4 addresses
such as `142.251.210.138` and timed out. Its logs also show unusable IPv6
attempts despite `dns.ipv6: false`; those appear separate from the verified
IPv4 address-selection failure. The active TUN uses `stack: mixed`, `auto-route: true`,
`auto-detect-interface: true`, and `strict-route: false`.

The active Clash Party runtime file `mihomo-party/work/config.yaml` confirms
the DNS/egress mismatch. It has `respect-rules: true`; its default `nameserver`
and `nameserver-policy` for `geosite:geolocation-!cn` send queries to
`8.8.8.8` and `1.1.1.1` using the `🌐 DNS 出口` group. It also sets
`direct-nameserver` to domestic resolvers but
`direct-nameserver-follow-policy: true`, so a DIRECT connection can still use
the matching DNS policy, as described in the [Mihomo DNS configuration](https://wiki.metacubex.one/en/config/dns/)
and [resolution flow](https://wiki.metacubex.one/en/config/dns/diagram/).
The GoogleCN routing rule sends the resulting Fonts connection DIRECT. Thus
the DNS query exits through the DNS proxy group while
the HTTPS request exits through the campus connection, which returns an
unreachable `142.251.x.x` answer on this path. This supports the user's
node-DNS hypothesis and identifies the mismatch as the cause.

The preferred general correction is to split DNS by egress. The runtime config
already has domestic `direct-nameserver`, proxy-group-routed `nameserver`, a
domestic `proxy-server-nameserver` for node hostnames, and
`respect-rules: true`. Change `direct-nameserver-follow-policy` to `false` so
DIRECT connections use the domestic direct resolver instead of inheriting the
`geosite:geolocation-!cn` proxy DNS policy. Proxy-routed domain connections
can continue sending the hostname through their selected proxy; the separate
`🌐 DNS 出口` group remains for DNS-server traffic. Mihomo documents these
behaviors in its [DNS configuration](https://wiki.metacubex.one/en/config/dns/)
and [resolution flow](https://wiki.metacubex.one/en/config/dns/diagram/).
An exact `nameserver-policy` for just `fonts.googleapis.com` and
`fonts.gstatic.com` is a narrower fallback if the user wants to keep the
current policy for other DIRECT domains. No live DNS setting has been changed.
With TUN on, Windows selects the Mihomo virtual adapter for default-route
traffic; the USB Ethernet adapter's `192.168.137.1` has no gateway and is not
a second internet exit.

This repository's external INI controls generated routing rules and groups;
another `DIRECT` rule cannot select a DNS resolver. A rules-only workaround
could instead send Fonts through a proxy, but would change the intended
traffic exit. To distribute the general fix through subscription updates,
change `direct-nameserver-follow-policy` to `false` in the source YAML or
converter base that produces the subscription's `dns` section. The cached
Clash Party profile and its effective `work/config.yaml` currently both carry
`true`, and no client override for this field was found.
After a subscription refresh, check that both files carry `false` and that a
fresh Fonts request follows `DIRECT` to a reachable local-DNS address.
Subconverter supports a custom YAML base through the external INI's
`clash_rule_base` setting; use it only with a complete base that preserves the
other profile fields and proxy groups. Its [official external-config example](https://github.com/tindy2013/subconverter/blob/master/base/config/example_external_config.ini)
documents the setting. The current INI does not activate a custom base. Its
published version also has no DNS section or `🌐 DNS 出口` group, although both
appear in the cached client profile. An additional conversion base or later
processing stage therefore supplies those settings. Replacing that base from
this INI requires preserving its other fields and defining the DNS exit group;
changing only a `ruleset=` line cannot make a direct route use local DNS.

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

## Claude 出口与 WebRTC 排查

规则优化可以减少误直连和不同分组造成的出口不一致，不能保证降低 Anthropic
账号风控或避免封号。第三方检测站的信任分数、机房/住宅分类、时区与语言提示，
不能当作 Anthropic 官方风控结论。规则也无法改变出口 IP 的 ASN、信誉、历史使用
情况或浏览器的时区、语言、Canvas/WebGL 指纹。

本模板已将 Claude/Anthropic 的明确目标域名放在国内进程直连规则之前，登录挑战
`challenges.cloudflare.com` 也走 AI。已列出的 Google、Cloudflare、Twilio 和
stunprotocol.org 公共 STUN 主机改为同走 AI，减少网页 HTTPS 与 WebRTC 使用不同
代理分组的情况。共享 STUN 无法识别来自哪个网页，因此使用这些主机的其他应用也
会受影响；国内应用仍保留更靠前的 STUN 进程直连例外。这些例外在不能识别下游
进程的路由器上不生效。

2026-10-31 复现并修复了地区跳转的一个具体成因：连接日志显示 claude.ai 的 TCP 请求
已由 `🤖 AI[🇺🇸 US-PPFLIGHT]`（美国出口）代理，但该节点不支持 UDP，Firefox 的
HTTP/3（QUIC，UDP 443）连接穿透全部规则回落为国内直连，页面随后仍以中国 IP 完成地区
判定并跳转 `app-unavailable-in-region`。模板已在 Anthropic 锁定块之后为同一组 AI
域名追加 UDP 443 REJECT 兜底：节点支持 UDP 时 QUIC 仍走 AI，不支持时浏览器回落
TCP，由既有 AI 规则代理。订阅刷新生效前，可临时在浏览器关闭 HTTP/3（Firefox 为
`network.http.http3.enable=false`，Chromium 系浏览器在 flags 中禁用 QUIC），或为
AI 分组改选支持 UDP 的节点。

若检测结果仍显示 Claude 使用代理出口、WebRTC/UDP 却使用国内出口，按以下顺序
检查客户端；仅更新这个 INI 不足以证明泄漏已修复：

1. 更新订阅后，在 **AI 分组直接选择一个固定节点**，确认没有选中 DIRECT、
   自动测速组或负载均衡组。AI 的默认回落仍是“节点选择”，其下级选择也可能自动
   改变出口；客户端保存的旧选择不会被新规则自动纠正。
2. 用 TUN/透明代理接管浏览器 UDP，确认未排除浏览器或相关 IPv4/IPv6 路由。
   系统 HTTP 代理不能完整接管 WebRTC UDP。若使用链式代理，确认最终出口和整条
   链路都支持 UDP；节点名称中的“家宽”不构成协议能力或 IP 属性的证明。
3. 在连接日志中同时查看 Claude HTTPS 与 STUN 的目标、命中规则、策略链和实际
   出口。Mihomo 文档说明，不支持 UDP 的代理会让 UDP 继续向后匹配规则，因此
   “域名已经写成 AI”不等于 UDP 已经由 AI 出站。参见
   [规则优先级](https://wiki.metacubex.one/en/config/rules/#priority)。
4. DNS 与直连/代理出口分别配置，并一致覆盖 IPv6。Windows 的
   `tun.strict-route: true` 可防止系统多网卡 DNS 泄漏，但不能单独证明 WebRTC
   无泄漏，参见 [TUN 配置](https://wiki.metacubex.one/en/config/inbound/tun/#strict-route)。
5. 不需要网页实时通话时，可在专用浏览器配置中禁用 WebRTC；需要通话时，应先验证
   UDP 代理或浏览器支持的中继策略，再复测。未知 STUN 域名、字面 IP、自定义端口
   和绕过 TUN 的连接不会因这份有限域名表而自动得到保护。模板未全局封禁 UDP，
   以免破坏通话、游戏及已有 ChatGPT Voice 规则。

重新打开检测页并在实际客户端复测：WebRTC 不应继续暴露非预期的国内公网地址；
如果禁用了 WebRTC，无法探测 UDP 地址属于预期结果，不代表 UDP 代理已经可用。
截图中单独显示的国内直连 IPv4 在分流配置下可以是预期行为，应与 WebRTC 获取到
国内公网地址的问题区分。STUN 如何发现公网地址可见
[MDN WebRTC 协议说明](https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API/Protocols#stun)。

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
