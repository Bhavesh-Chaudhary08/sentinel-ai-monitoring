// Fallback known-AI-domain list baked into the build.
// The authoritative list comes from GET /meta/ai-domains (Settings.known_ai_domains),
// cached here — options page and README document how to extend it.

export const FALLBACK_KNOWN_DOMAINS: string[] = [
  "chatgpt.com",
  "chat.openai.com",
  "openai.com",
  "gemini.google.com",
  "aistudio.google.com",
  "claude.ai",
  "anthropic.com",
  "copilot.microsoft.com",
  "github.com",
  "perplexity.ai",
  "poe.com",
  "character.ai",
  "you.com",
  "deepseek.com",
  "mistral.ai",
  "huggingface.co",
];

export function normalizeHost(raw: string): string {
  let value = (raw || "").trim().toLowerCase();
  for (const prefix of ["http://", "https://"]) {
    if (value.startsWith(prefix)) value = value.slice(prefix.length);
  }
  value = value.split("/")[0].split("?")[0].split("#")[0].split(":")[0];
  if (value.startsWith("www.")) value = value.slice(4);
  return value;
}

export function matchesDomain(host: string, domain: string): boolean {
  return host === domain || host.endsWith(`.${domain}`);
}
