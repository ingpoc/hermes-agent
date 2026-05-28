#!/usr/bin/env node
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { summarizeThread } from "./agent-feedback-routing.mjs";

const args = process.argv.slice(2);
const [id, status] = args.filter((a) => !a.startsWith("--"));
if (!id || !status) {
  console.error("Usage: scripts/agent-feedback-mark.mjs <work-id> <status> [agent-message] [--summary <thread-summary>] [--root <data-root>]");
  process.exit(2);
}

const summaryIndex = args.indexOf("--summary");
const messageParts = summaryIndex >= 0 ? args.slice(2, summaryIndex) : args.slice(2);
const explicitSummary = summaryIndex >= 0 ? args.slice(summaryIndex + 1).join(" ") : "";
const root = resolve(valueFor("--root") || process.cwd());
const queuePath = resolve(root, "data", "feedback-queue.json");
const queue = JSON.parse(await readFile(queuePath, "utf8"));
const item = queue.find((entry) => entry.id === id);

if (!item) {
  console.error(`Feedback batch not found: ${id}`);
  process.exit(1);
}

item.status = status;
item.workerStatus = status;
item.agentMessage = messageParts.join(" ");
if (explicitSummary) item.threadSummary = explicitSummary;
if (["done", "blocked", "canceled"].includes(status)) {
  item.lastProcessedAt = new Date().toISOString();
  if (!item.threadSummary) item.threadSummary = summarizeThread(item, item.agentMessage);
}
item.updatedAt = new Date().toISOString();
await writeFile(queuePath, `${JSON.stringify(queue, null, 2)}\n`);
console.log(JSON.stringify({
  id: item.id,
  markerId: item.markerId || item.marker?.id || item.payload?.comments?.[0]?.id,
  status: item.status,
  workerStatus: item.workerStatus
}, null, 2));

function valueFor(name) {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : null;
}
