#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const args = process.argv.slice(2);
const id = args.filter((a) => !a.startsWith("--"))[0];
if (!id) {
  console.error("Usage: scripts/agent-feedback-details.mjs <work-id> [--root <data-root>]");
  process.exit(2);
}

const root = resolve(valueFor("--root") || process.cwd());
const queuePath = resolve(root, "data", "feedback-queue.json");
const queue = JSON.parse(await readFile(queuePath, "utf8"));
const item = queue.find((entry) => entry.id === id);

if (!item) {
  console.error(`Feedback batch not found: ${id}`);
  process.exit(1);
}

console.log(JSON.stringify(item, null, 2));

function valueFor(name) {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : null;
}
