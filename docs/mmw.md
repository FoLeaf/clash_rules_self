# miaomiaowu（mmw）订阅模板

后端订阅转换跑在 DediRock 的 `miaomiaowu` 容器（妙妙屋 v0.10.1），
`/opt/mmw/rule_templates/` 下放**规则模板**，`/opt/mmw/subscribes/` 下放每个订阅的
YAML，`/opt/mmw/data/logs/mmw.log` 是排障入口。

## 为什么需要 `my_clash.yaml`

mmw 的模板槽位**按 YAML 解析**。把 `acl4ssr-ai-chain-v2.ini` 直接放进去会报：

```
[Subscription] 模板生成失败，回退到原始文件
  error="处理模板失败: yaml: line 5: mapping values are not allowed in this context"
```

第 5 行是 `; 分流约定:`，冒号让 YAML 以为这是 mapping key。更麻烦的是它**不报错给客户端**，
而是静默回退到 `subscribes/<名字>.yaml`，客户端拿到的还是旧规则，后端日志看着也算"正常"。

所以 INI 保持唯一事实来源，另存一份编译产物 `my_clash.yaml` 给 mmw 用。

## 生成与部署

```bash
# 1. 从服务器拉骨架（订阅当前实际服务的 YAML）
ssh -p 42387 root@107.174.123.74 \
  "cat /opt/mmw/subscribes/mirage.yaml" > mirage.yaml

# 2. 编译：只替换 rules 段，其余字节不动；--strip-proxies 清掉节点凭据
python -B tools/build_mmw_template.py --base mirage.yaml --strip-proxies -o my_clash.yaml

# 3. 校验（需要节点时先用带节点的版本）
mihomo -t -f my_clash.yaml -d .

# 4. 上传
scp -P 42387 my_clash.yaml root@107.174.123.74:/tmp/my_clash.yaml
ssh -p 42387 root@107.174.123.74 \
  "install -o 1000 -g 1000 -m 644 /tmp/my_clash.yaml /opt/mmw/rule_templates/my_clash.yaml"
```

上传后刷新一次订阅，日志应出现：

```
[模板生成] 模板处理完成  subscribe=mirage template=my_clash.yaml result_bytes=35281
```

出现 `模板生成失败，回退到原始文件` 就是又回到旧规则了。

## 几个坑

- **`*.txt.yaml` 规则集必须带 `format: text`**。转换器把 Loyalsoldier 的明文列表存成
  `direct.txt.yaml`/`gfw.txt.yaml`/`cncidr.txt.yaml`，但没写 `format`，mihomo 就按 YAML
  去解析纯文本，**规则数静默变成 0**（实测 `/providers/rules` 里三张表都是 0 条，
  补上后变成 110243 / 4453 / 9640）。后果很隐蔽：`direct.txt` 里 11 万条域名只有 625 条
  同时出现在 `ChinaDomain` 里，其余全部漏到代理；`gfw.txt` 永不命中；`cncidr.txt` 的
  国内 IP 兜底整段消失。`tools/build_mmw_template.py` 会自动补齐这三处，客户端侧
  `override/pin-google-single-egress.js` 也会按路径兜一层。
- **`proxies` 不用带**。实测模板里放 3 个节点，产出仍是 4 个：mmw 每次渲染都用自己节点表里的
  节点覆盖，并同步分组里的节点名。仓库里这份因此写成 `proxies: []`，避免把节点凭据推到公开仓库。
- **规则段的 `RULE-SET` tag 必须和 `rule-providers` 的键一致**。`Google.list` 对应的 tag 是
  `Google`，而 `cncidr.txt` 就保留扩展名，所以 tag 一律按 URL 从 provider 表反查，不靠文件名猜。
- **订阅之间共用同一个模板**。改一次，`mirage` 和 `sublinkpro` 同时生效（实测两者都变成
  35281 字节、434 条规则）。
- **模板失败不会自愈**。它只是回退，不会告警；`tests/test_mmw_template.py` 用"INI 重新编译
  后必须等于仓库里的 YAML"来卡住漂移。
