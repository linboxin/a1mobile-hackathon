import { requireEnv } from "./lib.mjs";

const BASE_URL = process.env.A1_API_BASE || "https://hack.a1mobile.com";
const teamKey = requireEnv("A1_TEAM_KEY");
const publicBaseUrl = requireEnv("PUBLIC_BASE_URL").replace(/\/$/, "");
const webhookUrl = `${publicBaseUrl}/voice`;

const response = await fetch(`${BASE_URL}/api/numbers/point`, {
  method: "POST",
  headers: { "X-Team-Key": teamKey, "Content-Type": "application/json" },
  body: JSON.stringify({ webhook_url: webhookUrl }),
});
const text = await response.text();

if (response.ok) {
  console.log(`Number pointed to ${webhookUrl}`);
  console.log(text);
  process.exit(0);
}

console.error(`A1 Mobile /api/numbers/point returned ${response.status}: ${text}`);

// The REST endpoint hides the real failure behind a bare 500. The portal's MCP
// server runs the same operation but reports the underlying error — fetch it so
// the organizers get an actionable message.
if (response.status >= 500) {
  try {
    const detail = await mcpPointNumber(teamKey, webhookUrl);
    console.error(`Underlying platform error (via MCP point_number): ${detail}`);
    console.error("This is a hack.a1mobile.com server-side failure — show this to the organizers.");
  } catch (error) {
    console.error(`(Could not fetch details via MCP: ${error.message})`);
  }
}
process.exit(1);

async function mcpPointNumber(key, url) {
  const mcpUrl = `${BASE_URL}/mcp/`;
  const headers = {
    "X-Team-Key": key,
    "Content-Type": "application/json",
    Accept: "application/json, text/event-stream",
  };
  const parseSse = async (res) => {
    const body = await res.text();
    const data = body.split("\n").find((line) => line.startsWith("data:"));
    return data ? JSON.parse(data.slice(5)) : JSON.parse(body);
  };

  const init = await fetch(mcpUrl, {
    method: "POST",
    headers,
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {
        protocolVersion: "2025-03-26",
        capabilities: {},
        clientInfo: { name: "a1-demo", version: "0.2" },
      },
    }),
  });
  const session = init.headers.get("mcp-session-id");
  if (!session) throw new Error("no MCP session id");
  headers["mcp-session-id"] = session;

  await fetch(mcpUrl, {
    method: "POST",
    headers,
    body: JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }),
  });

  const call = await fetch(mcpUrl, {
    method: "POST",
    headers,
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 2,
      method: "tools/call",
      params: { name: "point_number", arguments: { team_key: key, webhook_url: url } },
    }),
  });
  const result = await parseSse(call);
  return result?.result?.content?.[0]?.text ?? JSON.stringify(result);
}
