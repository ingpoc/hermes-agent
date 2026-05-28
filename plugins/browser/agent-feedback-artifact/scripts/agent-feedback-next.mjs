#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { classifyWorkItem, routeSummary } from "./agent-feedback-routing.mjs";

const args = process.argv.slice(2);
const root = resolve(valueFor("--root") || valueFor("--data") || process.cwd());
const queuePath = resolve(root, "data", "feedback-queue.json");
const queue = JSON.parse(await readFile(queuePath, "utf8"));
const item = queue.find((entry) => entry.status === "queued");

if (!item) {
  console.log(JSON.stringify({ item: null }, null, 2));
  process.exit(0);
}

console.log(JSON.stringify({
  item: summarizeItem(item)
}, null, 2));

function summarizeItem(item) {
  const marker = item.marker || item.payload?.comments?.[0] || {};
  const messages = Array.isArray(marker.messages) ? marker.messages : [];
  const latest = messages.filter((message) => message.role !== "agent" && message.text).at(-1);
  const route = classifyWorkItem(item);
  return {
    id: item.id,
    markerId: item.markerId || marker.markerId || marker.id,
    status: item.status,
    workerStatus: item.workerStatus || item.status,
    artifactPath: item.artifactPath || item.payload?.artifactPath,
    artifactTitle: item.artifactTitle || item.payload?.artifactTitle,
    artifactVersion: item.artifactVersion || item.payload?.artifactVersion,
    selector: item.selector || marker.selector,
    visibleText: item.visibleText || marker.selectedText || marker.text || "",
    latestUserMessage: item.latestUserMessage || latest?.text || marker.text || "",
    threadSummary: item.threadSummary || "",
    lastProcessedAt: item.lastProcessedAt || null,
    ...routeSummary(item, route),
    marker: {
      id: marker.id,
      markerId: item.markerId || marker.markerId || marker.id,
      text: marker.text,
      selector: marker.selector,
      status: marker.status || item.status
    }
  };
}

function valueFor(name) {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : null;
}
