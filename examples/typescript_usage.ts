/**
 * TypeScript plug-and-play demo (Node 18+).
 *
 *   trilith serve
 *   cd sdks/typescript && npx tsx ../../examples/typescript_usage.ts
 */

import { TrilithClient } from "../sdks/typescript/src/index.ts";

const client = new TrilithClient("http://127.0.0.1:8080");

await client.write({
  id: "ts-1",
  content: "Alice ships React and Node services.",
});

const memory = await client.memoryBlock("What does Alice ship?", 300);
const prompt = `Known context:\n${memory}\n\nUser: What does Alice ship?`;
console.log(prompt);
