# MiSub 原生后端方案

已验证 MiSub `v2.7.0` / `c6fd30c686b89fcf50c1368f4f36eca3ed622d36` 的真实
`renderClashFromIniTemplate` 生成路径。此方案不需要客户端 JavaScript 覆写，也不需要
修改或重新部署 MiSub 源码。

## 导入

1. 先把本次更新发布到 GitHub `FoLeaf/clash_rules_self` 的 `main` 分支。
   模板依赖下面三个文件，须一起发布：
   `rules/openai-ai.list`、`rules/overseas-ai.list`、`rules/cn-ip-fallback.list`。
   本地生成文件不会自动发布；使用其他仓库或分支时修改 `tools/build_misub.py` 的
   `RAW_BASE` 后重新生成。
2. MiSub 的转换引擎选择**内置**，分流方案选择**自定义规则模板**，导入或粘贴
   [`acl4ssr-ai-chain-misub.ini`](../acl4ssr-ai-chain-misub.ini)。也可发布该 INI 后使用
   自定义模板 URL。不要选择另一个 subconverter 后端后套用本说明。
3. 在当前订阅组中把 **UDP 转发**明确设为开启；使用全局设置时也须检查
   `builtinEnableUdp` 已开启。订阅 URL 的 `udp=false` 会覆盖开关；移除它或设为
   `udp=true`。这会在输出的节点上设置 `udp: true`。VLESS 服务端须支持 UDP 转发。
4. 在 MiSub 的 **DNS 覆写**输入框粘贴
   [`configs/misub-dns.yaml`](../configs/misub-dns.yaml)。这份内容保留了用户提供的
   DNS 配置，包括 `direct-nameserver-follow-policy: false`、本地节点解析和经
   `🚀 节点选择` 查询的 DoH。DNS 应填在这个独立入口，不能贴进 INI 规则区。
5. 保存并刷新客户端订阅。在输出 YAML 中确认 VLESS 的 `udp: true`、DNS 内容，
   以及代理规则后相邻的 REJECT。新模板与 DNS 均确认生效后，可取消客户端旧脚本绑定。

本地仓库修改没有更改已部署的 MiSub，也没有替用户修改客户端的 TUN、IPv6 或浏览器设置。

## 不依赖逻辑规则的 UDP 防泄漏

模板中的规则是成对的：

```ini
ruleset=🤖 AI,[]DOMAIN-SUFFIX,claude.com
ruleset=REJECT,[]DOMAIN-SUFFIX,claude.com
```

MiSub 会生成：

```yaml
rules:
  - DOMAIN-SUFFIX,claude.com,🤖 AI
  - DOMAIN-SUFFIX,claude.com,REJECT
```

TCP 和节点可转发的 UDP 命中第一条。Mihomo 在节点不支持 UDP 时会继续向后匹配，
随后被同目标的第二条拒绝，不会落到国内 IP 或进程直连。规则提供器同样成对：

```ini
ruleset=🤖 AI,https://raw.githubusercontent.com/FoLeaf/clash_rules_self/main/rules/openai-ai.list
ruleset=REJECT,https://raw.githubusercontent.com/FoLeaf/clash_rules_self/main/rules/openai-ai.list
```

同 URL 只生成一个原生规则提供器，由两条相邻 RULE-SET 规则引用。最终代理兜底后也
跟随 `MATCH,REJECT`，以免不支持 UDP 的最终节点导致隐式直连。国内 DIRECT 规则不加
拒绝副本；游戏、微软、苹果组原有的显式直连选项仍可使用。

## 为什么另做 MiSub 模板

已用真实生成器复现以下输出，并据此绕开兼容性问题：

- 内联 AND 被截断成 `AND,((NETWORK,REJECT`，所以采用同条件 REJECT，而不写 AND。
- 内联 IP / GEOIP 的 `no-resolve` 被丢弃，所以把 OpenAI IP 和最终 GEOIP 条件保留在
  原生 classical 提供器的载荷中。核心测试确认早期 IP 规则不会为无关域名查询海外 DNS。
- MiSub 会剥离 `quanx:` 前缀并直接加载远程列表，不会把 Quantumult X 的 HOST 规则
  转成 Mihomo DOMAIN。因此 `rules/overseas-ai.list` 保存规范化的目标规则快照，保留
  原始 `no-resolve`，且不引入整个 Claude/Codex/IDE 进程代理。
- MiSub 对首选节点的 `^完整名称$` 识别不同，生成模板改用显式名称引用；缺失节点会被
  后端清理，仍回落节点选择。

这些问题来自 MiSub 当前的
[INI 解析器](https://github.com/imzyb/MiSub/blob/c6fd30c686b89fcf50c1368f4f36eca3ed622d36/functions/modules/subscription/template-parsers/ini-template-parser.js)
与 [Clash 输出器](https://github.com/imzyb/MiSub/blob/c6fd30c686b89fcf50c1368f4f36eca3ed622d36/functions/modules/subscription/template-renderers/render-clash.js)。
UDP 转发开关见其
[节点转换实现](https://github.com/imzyb/MiSub/blob/c6fd30c686b89fcf50c1368f4f36eca3ed622d36/functions/utils/url-to-clash.js)。

## 更新与验证

修改主 INI 后，运行 `python -B tools/build_misub.py` 重建派生模板。要刷新海外 AI 快照，
使用 `python -B tools/build_misub.py --refresh-ai`。域名与 IP 都来自仓库/上游清单，
该脚本仅在维护时运行，客户端和 MiSub 都不执行它。

离线检查：

```powershell
python -B -m unittest discover -s tests -v
```

真实后端与核心检查需要一个安装了生产依赖的 MiSub 检出目录：

```powershell
$env:MISUB_SOURCE = 'C:\path\to\MiSub'
$env:MIHOMO_BIN = 'C:\path\to\mihomo.exe'
python -B -m unittest discover -s tests -v
```

测试实际执行 MiSub 生成器，并使用隔离的 Mihomo 配置和本地 UDP / DNS 接收器，
覆盖 Claude、STUN、字面 IP、最终兜底、可用 UDP 出口、国内直连和 no-resolve。
它验证生成与路由行为；远端节点是否允许 UDP 转发，以及设备是否完整接管 IPv4/IPv6、
WebRTC 和 DNS，仍以部署后的连接日志和浏览器检测为准。

2026-11-01 验证记录：47 项测试通过；实际 MiSub 输出 367 条规则、48 个原生规则
提供器。校验时拉取了上游提供器，并对尚未发布的本仓库规则使用本地内容，隔离后的
完整配置通过 Mihomo v1.19.33 的 `-t` 检查。新文件发布前，远程 URL 仍不能代表本地内容；
MiSub 也可能把 GitHub raw URL 改写为 jsDelivr，首次发布后需检查 CDN 缓存和提供器更新。
