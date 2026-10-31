// Inject QUIC fallback REJECT rules after the pinned AI domain rules.
// The client converter keeps only "TYPE,VALUE" from inline INI rules, so logic
// rules containing commas cannot live there and are added after conversion.
// When the AI node cannot carry UDP (this subscription ships udp=false),
// rejecting UDP 443 makes browsers fall back to TCP, which the AI rules proxy.
function main(config) {
  const suffixes = [
    "openai.com", "chatgpt.com", "chat.com", "sora.com",
    "oaistatic.com", "oaiusercontent.com", "oaistatsig.com", "openaimerge.com",
    "claude.ai", "claude.com", "claude.app", "claude.dev",
    "claude.new", "claude.site", "anthropic.com",
    "claudeusercontent.com", "claudemcpclient.com", "claudemcpcontent.com",
  ];
  const exact = [
    "cdn.platform.openai.com", "anthropic.auth0.com",
    "anthropic.com.cdn.cloudflare.net", "servd-anthropic-website.b-cdn.net",
    "anthropic-com.ghost.io",
  ];
  const reject = [
    ...suffixes.map((d) => `AND,((NETWORK,UDP),(DST-PORT,443),(DOMAIN-SUFFIX,${d})),REJECT`),
    ...exact.map((d) => `AND,((NETWORK,UDP),(DST-PORT,443),(DOMAIN,${d})),REJECT`),
  ];
  const rules = config.rules || (config.rules = []);
  const pin = rules.findIndex((r) => typeof r === "string"
    && r.startsWith("DOMAIN,anthropic-com.ghost.io,"));
  if (pin !== -1) {
    rules.splice(pin + 1, 0, ...reject);
    return config;
  }
  const tail = rules.findIndex((r) => typeof r === "string"
    && (r.startsWith("MATCH,") || r.startsWith("FINAL,")));
  if (tail === -1) rules.push(...reject);
  else rules.splice(tail, 0, ...reject);
  return config;
}
