const BASE_URL = process.env.A1_API_BASE || "https://hack.a1mobile.com";

export function requireEnv(name) {
  const value = process.env[name];
  if (!value || value.includes("replace_me")) {
    console.error(`Missing ${name}. Fill it in .env (see .env.example).`);
    process.exit(1);
  }
  return value;
}

export async function a1(path, body) {
  const teamKey = requireEnv("A1_TEAM_KEY");
  const response = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "X-Team-Key": teamKey,
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const text = await response.text();
  if (!response.ok) {
    console.error(`A1 Mobile ${path} returned ${response.status}: ${text}`);
    process.exit(1);
  }
  return text;
}
