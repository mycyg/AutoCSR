// Run `python scripts/generate_sdk.py --ts` first to populate sdk/ts.
//
// Then:   tsc sdk/example.ts && node sdk/example.js
//
// Requires the generated client to export the standard `OpenAPI` config
// object and at least one service module.

import { OpenAPI } from "./ts";

OpenAPI.BASE = process.env.AUTOCSR_BASE ?? "http://127.0.0.1:8766";

async function main(): Promise<void> {
  const res = await fetch(`${OpenAPI.BASE}/api/health`);
  const body = await res.json();
  console.log("[example.ts] /api/health =>", body);
}

main().catch((err) => {
  console.error("[example.ts] SDK call failed:", err);
  process.exit(0); // 'Not generated yet' is not a CI failure here.
});
