// LAP Node.js Echo Agent. Stdout is protocol-only.
"use strict";

const readline = require("node:readline");

const AGENT_ID = "org.lap.echo-agent-node";
const AGENT_VERSION = "0.1.0";
let sequence = 0;

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function asObject(value) {
  return isObject(value) ? value : {};
}

function emit(messageType, payload, correlationId = "", run = null) {
  sequence += 1;
  const frame = {
    lap: "0.1",
    id: `node-echo-${sequence}`,
    producer: AGENT_ID,
    seq: sequence,
    type: messageType,
    payload,
  };
  if (correlationId) frame.correlation_id = correlationId;
  if (isObject(run)) frame.run = run;
  process.stdout.write(`${JSON.stringify(frame)}\n`);
}

function handle(frame) {
  const messageType = frame.type;
  if (messageType === "agent.hello") {
    emit("agent.welcome", {
      selected_lap: "0.1",
      profiles: ["lap-local/0.1"],
      agent_id: AGENT_ID,
      version: AGENT_VERSION,
      max_concurrency: 1,
    }, String(frame.id || ""));
    return true;
  }
  if (messageType === "run.start") {
    const run = asObject(frame.run);
    const payload = asObject(frame.payload);
    const input = asObject(payload.input);
    const text = typeof input.text === "string" ? input.text : "";
    emit("run.accepted", { capability: payload.capability }, String(frame.id || ""), run);
    emit("run.progress", { phase: "agent", message: "Processing requested task." }, "", run);
    emit("run.result", {
      status: "succeeded",
      summary: "Echo complete.",
      output: { text },
    }, "", run);
    return true;
  }
  if (messageType === "run.cancel") {
    emit("run.result", {
      status: "cancelled",
      summary: "Run cancelled.",
      error: { code: "LAP-401", message: "Cancellation requested.", retryable: false },
    }, "", asObject(frame.run));
    return true;
  }
  return messageType !== "agent.shutdown";
}

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
let stopped = false;
input.on("line", (raw) => {
  if (stopped) return;
  let frame;
  try {
    frame = JSON.parse(raw);
    if (!isObject(frame)) throw new Error("frame must be an object");
  } catch (_error) {
    process.stderr.write("invalid LAP frame\n");
    process.exitCode = 2;
    stopped = true;
    input.close();
    return;
  }
  if (!handle(frame)) {
    stopped = true;
    input.close();
  }
});
