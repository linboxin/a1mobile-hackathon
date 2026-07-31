import { a1 } from "./lib.mjs";

const phone = process.argv[2];
if (!phone || !phone.startsWith("+")) {
  console.error("Usage: npm run verify -- +15551234567");
  console.error("Sends an OTP text to that phone so it can consent to your agent.");
  process.exit(1);
}

const result = await a1("/api/verified-numbers", { phone });
console.log(`OTP sent to ${phone}. Check that phone for the code, then run:`);
console.log(`  npm run confirm -- ${phone} <code>`);
console.log(result);
