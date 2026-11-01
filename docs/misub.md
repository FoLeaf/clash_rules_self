# 原 INI 在 MiSub 中的用法

继续使用 [`acl4ssr-ai-chain-v2.ini`](../acl4ssr-ai-chain-v2.ini)。已撤回分组改动，
全部 11 个分组与修改前的 `54ceb00` 完全一致，包括名称、类型、成员、DIRECT 选项、
默认顺序及首选节点正则。专用 INI 和生成器已删除。

## 配置

1. MiSub 使用内置引擎，规则模板仍选择原来的 INI 文件或它的原 URL，不需要换文件名。
2. 保留已有 DNS。用户提供的 DNS 已有 `direct-nameserver-follow-policy: false`，
   国内直连解析与代理 DoH 分开；`configs/misub-dns.yaml` 仅作为该配置的保存副本。
3. VLESS 需要代理 UDP 时，在 MiSub 开启 UDP 转发，并检查输出节点的 `udp: true`。
   这项节点能力由后端设置，规则不会改写节点参数或分组。
4. 更新订阅，检查 Claude 命中原有 AI 分组，国内服务和 Steam 下载仍直连。
   不需要额外绑定客户端 JavaScript。其他负责创建链式节点的既有配置仍由用户保留。

## 规则调整

国内服务直连、Steam 定位与下载直连、游戏/微软/苹果等原分流均保留。已知海外目标
先于国内进程兜底，避免微信等内嵌浏览器误直连。每条代理规则紧跟同条件 REJECT：

```ini
ruleset=🤖 AI,[]DOMAIN-SUFFIX,claude.com
ruleset=REJECT,[]DOMAIN-SUFFIX,claude.com
```

TCP 与可代理的 UDP 命中第一条；节点不支持 UDP 时命中第二条，避免继续落到直连。
如果用户在原分组中主动选择 DIRECT，规则照常执行该选择。

MiSub 会截断内联 AND、丢弃内联 `no-resolve`，也不会转换 Quantumult X HOST 规则。
因此只对必要的规则源做适配：OpenAI 语音 IP 和最终 GEOIP 通过原生 classical 提供器
保留 `no-resolve`；海外 AI 目标清单使用已转为 Mihomo 格式的 `rules/overseas-ai.list`。
OpenAI/Claude 核心域名仍保留原文件的内联规则、注释和分区。

## 验证

`tests/fixtures/original-groups.txt` 保存修改前的 11 条分组，测试逐字比较原 INI，
并检查可选兼容脚本不改写分组。常规测试使用：

```powershell
python -B -m unittest discover -s tests -v
```

设置 `MISUB_SOURCE` 和 `MIHOMO_BIN` 可启用真实 MiSub 生成器与本地 UDP/DNS 实包测试。
验证过的 MiSub 源码为 `c6fd30c686b89fcf50c1368f4f36eca3ed622d36`；未更改已部署的
MiSub 源码，也未更改客户端设置。
