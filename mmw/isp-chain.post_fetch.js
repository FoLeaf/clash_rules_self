// post_fetch: ISP 住宅落地 → 两级链路
// mmw 会在脚本执行前剥掉模板里的 proxy-providers，所以 provider 由本脚本自己注入
// 生成的组：🚀 前置 / 🌄 落地ISP (双跳) / 🛟 落地回落 (双跳)
// 没有可用前置时原样返回，绝不改坏订阅
function main(config) {
  var FRONT = "🚀 前置";
  var LAND = "🌄 落地ISP (双跳)";
  var WRAP = "🛟 落地回落 (双跳)";
  var BASE = "🚀 节点选择";
  var PROVIDER = "ISP-静态住宅";
  var ISP_URL = "https://ai01.teleapi.top/s/sPsAVvHkLA6Z";
  var FRONT_RE = /PPFLIGHT|SG-AWS|MoeCloud/i;

  var proxies = config.proxies || [];
  var groups = config["proxy-groups"] || [];

  var front = proxies.filter(function (p) {
    return p && FRONT_RE.test(p.name || "");
  }).map(function (p) { return p.name; });
  if (!front.length) return config;
  // SG-AWS 排第一作为默认前置：moe 已宕机、IPv6 备用无出口
  front.sort(function (a, b) {
    return (a.indexOf("SG-AWS") >= 0 ? 0 : 1) - (b.indexOf("SG-AWS") >= 0 ? 0 : 1);
  });

  var providers = config["proxy-providers"] || {};
  providers[PROVIDER] = {
    type: "http",
    url: ISP_URL,
    interval: 86400,
    path: "./providers/isp-static.yaml",
    filter: "-静态",
    override: { "dialer-proxy": FRONT }
  };
  config["proxy-providers"] = providers;

  // 前置链路上的组仍然保留，只是不挂回落：
  // 回落 → 落地ISP → 前置 → 节点选择 → 回落 会成环
  var NO_WRAP = [BASE, "♻️ 自动选择", "⚖️ 负载均衡"];
  var kept = groups.filter(function (g) {
    return g && [FRONT, LAND, WRAP].indexOf(g.name) < 0;
  });

  var out = [
    { name: FRONT, type: "select", proxies: front },
    { name: LAND, type: "select", use: [PROVIDER] },
    { name: WRAP, type: "fallback", proxies: [LAND, BASE], lazy: true, interval: 3600 }
  ];
  for (var i = 0; i < kept.length; i++) {
    var g = kept[i];
    if (NO_WRAP.indexOf(g.name) < 0) {
      if (!g.proxies) g.proxies = [];
      if (g.proxies.indexOf(WRAP) < 0) g.proxies.push(WRAP);
    }
    out.push(g);
  }
  config["proxy-groups"] = out;
  return config;
}
