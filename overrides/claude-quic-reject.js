// Keep the filename for existing Clash Party override bindings.
// Reject UDP immediately after each proxy rule if its exit cannot carry UDP.
// The client converter keeps only "TYPE,VALUE" from inline INI rules, so logic
// rules containing commas cannot live there and are added after conversion.
// Covers QUIC, STUN, literal IPs, expanded lists and the final proxy fallback.
// UDP-capable exits match the original rule; DIRECT destinations stay DIRECT.
function main(config) {
  // VLESS can carry UDP datagrams inside its existing TCP/TLS/WS connection.
  // The user's policy enables that path even when a subscription says udp=false.
  // Preserve packet-encoding: raw/default, xudp and packetaddr require matching
  // server support. Transport choice alone does not imply TCP-only forwarding.
  for (const proxy of config.proxies || []) {
    if (proxy.type === "vless") proxy.udp = true;
  }
  // DIRECT must resolve at its own exit instead of inheriting overseas DNS
  // policy. Keep the client's chosen domestic/bootstrap/proxy resolvers.
  if (config.dns && (config.dns["direct-nameserver"] || []).length) {
    config.dns["direct-nameserver-follow-policy"] = false;
  }
  // Subscription refreshes can restore DIRECT members. Keep overseas-only
  // selectors closed; Apple/Microsoft/games retain their explicit direct option.
  const proxyOnly = new Set([
    "🚀 节点选择", "📲 电报消息", "🤖 AI", "🎬 国外流媒体", "🌐 国外社交", "🐟 漏网之鱼",
  ]);
  const groups = new Map((config["proxy-groups"] || []).map((group) => [group.name, group]));
  const directNames = new Set(["DIRECT", ...(config.proxies || [])
    .filter((proxy) => proxy.type === "direct").map((proxy) => proxy.name)]);
  // Follow nested selectors too: an automatic group containing DIRECT would
  // otherwise reopen the same leak through the node-selection group.
  for (const name of proxyOnly) {
    for (const member of groups.get(name)?.proxies || []) {
      if (groups.has(member)) proxyOnly.add(member);
    }
  }
  for (const group of config["proxy-groups"] || []) {
    if (!proxyOnly.has(group.name) || !Array.isArray(group.proxies)) continue;
    group.proxies = group.proxies.filter((name) => !directNames.has(name));
    if (!group.proxies.length && !(group.use || []).length) group.proxies = ["REJECT"];
  }
  const rules = (config.rules || []).map((rule) => {
    // Restore the flags known to be discarded by the client converter. Early
    // voice IP pins must not force DNS queries for every unrelated domain.
    if (typeof rule === "string" && (/^IP-CIDR6?,[^,]+,🤖 AI$/.test(rule)
        || rule === "GEOIP,CN,DIRECT")) return `${rule},no-resolve`;
    return rule;
  });
  const guards = new Map();
  for (const rule of rules) {
    if (typeof rule !== "string") continue;
    const fields = rule.split(",");
    const flags = [];
    while (["no-resolve", "src"].includes(fields[fields.length - 1])) {
      flags.unshift(fields.pop());
    }
    const policy = fields.pop();
    if (!policy || fields.length === 0
        || ["DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE"].includes(policy)) continue;
    const condition = fields.join(",");
    const guard = ["MATCH", "FINAL"].includes(condition)
      ? "NETWORK,UDP,REJECT"
      : `AND,((NETWORK,UDP),(${condition}${flags.length ? "," + flags.join(",") : ""})),REJECT`;
    guards.set(rule, guard);
  }
  // Consume only an adjacent copy of our guard. Preserve independent REJECT
  // rules, including ones placed earlier by another client override.
  config.rules = [];
  for (let i = 0; i < rules.length; ++i) {
    const rule = rules[i];
    config.rules.push(rule);
    if (!guards.has(rule)) continue;
    const guard = guards.get(rule);
    config.rules.push(guard);
    if (rules[i + 1] === guard) ++i;
  }
  return config;
}
