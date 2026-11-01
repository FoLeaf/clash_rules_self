# Clash Rules for Mainland China

`acl4ssr-ai-chain-v2.ini` is a subconverter external configuration, not a
standalone Clash/Mihomo YAML file. Supply it as the converter's `config`
parameter together with your subscription. A working proxy subscription is
still required.

## MiSub：无客户端脚本方案

MiSub 内置引擎使用 [`acl4ssr-ai-chain-misub.ini`](acl4ssr-ai-chain-misub.ini)，
在后端开启 UDP 转发，并把 [`configs/misub-dns.yaml`](configs/misub-dns.yaml) 填入
MiSub 的 DNS 覆写入口。代理规则与同目标 REJECT 成对生成，不需要客户端脚本，
也不需要修改 MiSub 源码。须先发布模板依赖的 `rules/` 文件。
完整步骤、真实生成器验证和维护方式见 [`docs/misub.md`](docs/misub.md)。

下文的 `acl4ssr-ai-chain-v2.ini` 与 JavaScript 绑定说明适用于原有转换方案；
使用 MiSub 专用模板时，按上面的后端方案配置即可。

## 使用方式（2026-11-01 更新）

更新订阅转换用的 INI 后，还须在 Clash Party 当前订阅上绑定
[`overrides/claude-quic-reject.js`](overrides/claude-quic-reject.js)，并重新激活订阅。
该脚本保留原文件名以兼容已有绑定，现已覆盖全部代理规则的 UDP 回落，并在已有
`direct-nameserver` 时设置 `direct-nameserver-follow-policy: false`。
脚本应在其他新增节点/规则的覆写之后执行；仅更新 INI 不会安装或更新客户端本地脚本。

国内域名保持直连；微信、QQ 等进程仅兜底尚未识别的目标，内嵌网页先按目标域名分流。
Claude/OpenAI 优先走 AI；公共 STUN 也走 AI，包括国内进程对这些主机的请求。
节点选择、AI、社交、流媒体、电报和漏网之鱼移除 DIRECT；游戏、微软、苹果保留可选直连。
没有可用代理时应拒绝连接，不能自动直连。国内应用若依赖这些公共 STUN，而 AI 节点不支持
UDP，相关通话会被拒绝；使用支持 UDP 的出口，或为确认可直连的国内服务添加精确目标规则。

这些修改已通过本地核心回归；实际设备仍须启用完整 TUN/透明接管、配置代理 DNS 与 IPv6，
并检查连接日志和浏览器 WebRTC。下文的历史排查记录说明旧配置的行为。

## VLESS 的 UDP 经 TCP 隧道转发

VLESS 使用 `network: tcp`、TLS、WebSocket 等传输时，可以在已有连接里封装 UDP。
本覆写会把实际 `proxies` 中 VLESS 节点的 `udp` 设为 `true`，包括订阅原来标为
`udp: false` 的节点；保留 `network`、TLS/REALITY、链路设置和已有的 `packet-encoding`。
QUIC、STUN 等 UDP 数据因此可以经选定 VLESS 节点的 TCP 隧道出站，无需本机直连。
这项行为是 UDP 封装，QUIC 到服务端后仍是 QUIC，并未转换成 HTTP/2。

`packet-encoding: xudp`、`packetaddr` 需要服务端支持；未指定时保留 Mihomo 默认行为，
不强行更换封装。服务端还须允许 UDP 转发；只开放节点的 TCP 监听端口也能承载这条
隧道，但“节点能连 TCP”本身不足以证明服务端允许转发 UDP。参见
[Mihomo VLESS 配置](https://wiki.metacubex.one/en/config/proxies/vless/)。
通过 `proxy-providers` 在启动后动态加载的节点不在这次脚本遍历的 `proxies` 中；
这类订阅须在对应 provider 的覆写中配置 UDP 能力。

如果协议或服务端确实不能代理 UDP，普通 UDP 无法由规则通用转换成 TCP。
网页 HTTP/3 可以在 QUIC 不可用后由浏览器重试 HTTP/2 或 HTTP/1.1，这些 TCP 连接
继续命中相同 AI/代理规则；具体重试由浏览器决定。STUN、游戏等只有在应用支持
TCP/TURN 中继时才有相应替代路径。参见
[RFC 9114 §3.1](https://www.rfc-editor.org/rfc/rfc9114.html#section-3.1)。
覆写保留不支持 UDP 时的 REJECT 兜底；服务端拒绝封装时也不得改走 DIRECT。

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
- ChatGPT Voice's 402 currently published IP ranges are pinned to AI with
  `no-resolve`, before process fallbacks. They come from the
  [official voice JSON](https://openai.com/chatgpt-voice.json), retrieved on
  2026-11-01 (source creation time: 2026-10-27). Refresh both the canonical list
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
- UDP fallback protection must be installed after conversion. The client converter
  cannot preserve inline logical rules, so bind
  [`overrides/claude-quic-reject.js`](overrides/claude-quic-reject.js) in Clash Party.
  The script adds a matching UDP REJECT immediately after each proxy rule,
  including domain keywords, literal IPs, RULE-SETs and MATCH. Supported UDP
  takes the original proxy rule; unsupported UDP stops at REJECT before any
  later DIRECT rule. This covers all ports, including QUIC and STUN. Known
  domestic DIRECT rules retain their original behavior. The script preserves
  `no-resolve` inside the logical condition and is safe to apply repeatedly.
  It restores converter-dropped `no-resolve` on AI IP pins and the CN GEOIP
  fallback, so early voice rules do not resolve unrelated domains.
- Microsoft and Apple groups default to DIRECT, but can be switched to a proxy.
- Games and unmatched traffic default to node selection. Games retain an
  explicit DIRECT option; overseas-only groups and unmatched traffic do not.
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

Existing clients can restore saved selections. Reimport the override and
reactivate the subscription; confirm overseas-only groups no longer offer
DIRECT and choose a fixed AI exit for session-sensitive services.

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
current policy for other DIRECT domains. The runtime override now applies this field when `direct-nameserver` is set;
no live client setting was changed while editing this repository.
With TUN on, Windows selects the Mihomo virtual adapter for default-route
traffic; the USB Ethernet adapter's `192.168.137.1` has no gateway and is not
a second internet exit.

This repository's external INI controls generated routing rules and groups;
another `DIRECT` rule cannot select a DNS resolver. A rules-only workaround
could instead send Fonts through a proxy, but would change the intended
traffic exit. To distribute the general fix through subscription updates,
change `direct-nameserver-follow-policy` to `false` in the source YAML or
converter base that produces the subscription's `dns` section. At the time of that capture, the cached
Clash Party profile and effective `work/config.yaml` both carried `true`. The
repository override now changes it to `false` when a direct resolver exists;
install the updated script in the client to apply it.
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
会受影响；已知公共 STUN 优先于国内进程兜底；国内服务仍按国内目标域名直连。

2026-10-31 的日志确认了一处路由缺陷：Claude TCP 请求走 AI，美国出口节点的
`udp: false` 导致浏览器 UDP 443 请求回落 DIRECT。日志不能证明 QUIC 握手成功或
地区跳转由此造成；地区限制是否解除须通过浏览器复测确认。

客户端转换器会把 INI 内联 AND 规则截断成 `AND,((NETWORK,REJECT`，因此兜底须在
转换完成后注入，见 [`overrides/claude-quic-reject.js`](overrides/claude-quic-reject.js)。
脚本从实际配置的每一条代理规则生成 UDP REJECT，紧跟原规则插入，覆盖全部端口、
域名/关键词/IP/RULE-SET 与最终代理兜底。支持 UDP 的出口仍命中原规则；不支持时拒绝
连接，QUIC 浏览器可回落 TCP。STUN 被拒绝表示该路径不可用，不代表 UDP 已代理成功。
无域名的连接由 IP、进程和最终规则继续分流；未知国内 IP 仍可能命中国内 IP 直连规则，
任意 STUN/WebRTC 目标和绕过 TUN 的流量仍需浏览器与客户端共同控制。
脚本同时清除标准海外专用组的 DIRECT 成员；保留游戏、微软和苹果组的显式直连。

在 Clash Party 的「覆写」页编辑或导入本地 JavaScript 脚本，再通过当前订阅的
「编辑信息 → 覆写」选择该脚本并保存。不要在客户端运行时直接修改 profile.yaml：
内存状态可能覆盖文件。重新激活订阅后，检查有效配置包含挑战域名及 STUN 的 AND/REJECT 规则，
并检查新连接日志中不支持的 UDP 命中 REJECT、TCP 仍走 AI。仅更新 INI 不会挂载此脚本。

若检测结果仍显示 Claude 使用代理出口、WebRTC/UDP 却使用国内出口，按以下顺序
检查客户端；仅更新这个 INI 不足以证明泄漏已修复：

1. 更新订阅后，在 **AI 分组直接选择一个固定节点**，确认没有选中 DIRECT、
   自动测速组或负载均衡组。AI 的默认回落仍是“节点选择”，其下级选择也可能自动
   改变出口；更新后的专用分组与覆写已移除 DIRECT 选项。
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
   和绕过 TUN 的连接不会因这份有限域名表而自动得到保护。覆写按目标策略拒绝代理节点不支持的 UDP，
   国内 DIRECT 目标仍可使用 UDP；ChatGPT Voice 需要支持 UDP 的 AI 出口。

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

Offline override checks require Node.js on PATH and execute the JavaScript entry point.
For actual core regression checks, set `MIHOMO_BIN` to your core executable:

```powershell
$env:MIHOMO_BIN = 'C:\path\to\mihomo.exe'
python -B -m unittest discover -s tests -v
```

The core tests launch isolated temporary configurations with local UDP receivers
and DNS responders. They reproduce unsupported-UDP fallthrough and DIRECT DNS
policy inheritance without touching the running client or contacting internet
services. Without `MIHOMO_BIN` (or `mihomo` on PATH), these tests are skipped.
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
