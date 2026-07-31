import { a1 } from "./lib.mjs";

const [phone, code] = process.argv.slice(2);
if (!phone || !phone.startsWith("+") || !code) {
  console.error("Usage: npm run confirm -- +15551234567 123456");
  process.exit(1);
}

const result = await a1("/api/verified-numbers/confirm", { phone, code });
console.log(`${phone} is now verified. You can call/text it from your agent.`);
console.log(result);
