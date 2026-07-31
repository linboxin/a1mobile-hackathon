const teamKey = process.env.A1_TEAM_KEY;
const publicBaseUrl = process.env.PUBLIC_BASE_URL?.replace(/\/$/, "");

if (!teamKey || !publicBaseUrl) {
  console.error("Set A1_TEAM_KEY and PUBLIC_BASE_URL before running this command.");
  process.exit(1);
}

const webhookUrl = `${publicBaseUrl}/voice`;
const response = await fetch("https://hack.a1mobile.com/api/numbers/point", {
  method: "POST",
  headers: {
    "X-Team-Key": teamKey,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ webhook_url: webhookUrl }),
});

const text = await response.text();

if (!response.ok) {
  console.error(`A1 Mobile returned ${response.status}: ${text}`);
  process.exit(1);
}

console.log(`Number pointed to ${webhookUrl}`);
console.log(text);
