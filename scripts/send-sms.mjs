import { a1 } from "./lib.mjs";

const to = process.argv[2];
const body = process.argv.slice(3).join(" ") || "hello from my agent";
if (!to || !to.startsWith("+")) {
  console.error('Usage: npm run sms -- +15551234567 "your message"');
  console.error("The destination must already be OTP-verified (npm run verify / confirm).");
  process.exit(1);
}

const result = await a1("/api/sms", { to, body });
console.log(`SMS sent to ${to}: ${body}`);
console.log(result);
