// LAP Node.js external orchestrator. Stdout is protocol-only.
"use strict";

const readline = require("node:readline");

const AGENT_ID = "org.lap.orchestrator-agent-node";
const AGENT_VERSION = "0.1.0";
const EXTENSION_KEY = "io.github.lambda-harness.lap.workflow.orchestrator";
const AGENT_ID_PATTERN = /^[a-z][a-z0-9.-]{2,127}$/;
const CAPABILITY_PATTERN = /^[a-z][a-z0-9._-]{2,127}$/;
let sequence = 0;

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function asObject(value) {
  return isObject(value) ? value : {};
}

function hasExactKeys(value, keys) {
  if (!isObject(value)) return false;
  const actual = Object.keys(value).sort();
  return actual.length === keys.length && actual.every((key, index) => key === keys[index]);
}

function emit(messageType, payload, correlationId = "", run = null) {
  sequence += 1;
  const frame = {
    lap: "0.1",
    id: `node-orchestrator-${sequence}`,
    producer: AGENT_ID,
    seq: sequence,
    type: messageType,
    payload,
  };
  if (correlationId) frame.correlation_id = correlationId;
  if (isObject(run)) frame.run = run;
  process.stdout.write(`${JSON.stringify(frame)}\n`);
}

function dispatchFromContext(payload) {
  const context = asObject(payload.context);
  const extensions = asObject(context.extensions);
  const extension = extensions[EXTENSION_KEY];
  if (!hasExactKeys(extension, ["allowed_dispatches", "version"]) || extension.version !== "0.2") {
    throw new Error("invalid context");
  }
  const allowed = extension.allowed_dispatches;
  if (!Array.isArray(allowed) || allowed.length === 0) throw new Error("invalid context");

  let previousAgentId = "";
  let selectedAgentId = "";
  let selectedCapability = "";
  for (let index = 0; index < allowed.length; index += 1) {
    const target = allowed[index];
    if (!hasExactKeys(target, ["agent_id", "capabilities"])) throw new Error("invalid context");
    const agentId = target.agent_id;
    const capabilities = target.capabilities;
    if (typeof agentId !== "string" || !AGENT_ID_PATTERN.test(agentId)) throw new Error("invalid context");
    if (previousAgentId && agentId <= previousAgentId) throw new Error("invalid context");
    if (!Array.isArray(capabilities) || capabilities.length === 0) throw new Error("invalid context");

    let previousCapability = "";
    for (const capability of capabilities) {
      if (typeof capability !== "string" || !CAPABILITY_PATTERN.test(capability)) {
        throw new Error("invalid context");
      }
      if (previousCapability && capability <= previousCapability) throw new Error("invalid context");
      previousCapability = capability;
    }
    if (index === 0) {
      selectedAgentId = agentId;
      selectedCapability = capabilities[0];
    }
    previousAgentId = agentId;
  }

  return {
    dispatch: [{
      agent_id: selectedAgentId,
      capability: selectedCapability,
      input: Object.prototype.hasOwnProperty.call(payload, "input") ? payload.input : {},
    }],
  };
}

function handle(frame) {
  const messageType = frame.type;
  if (messageType === "agent.hello") {
    emit("agent.welcome", {
      selected_lap: "0.1",
      profiles: ["lap-local/0.1", "lap-workflow/0.2"],
      agent_id: AGENT_ID,
      version: AGENT_VERSION,
      max_concurrency: 1,
    }, String(frame.id || ""));
    return true;
  }
  if (messageType === "run.start") {
    const run = asObject(frame.run);
    const payload = asObject(frame.payload);
    emit("run.accepted", { capability: payload.capability }, String(frame.id || ""), run);
    let output;
    try {
      output = dispatchFromContext(payload);
    } catch (_error) {
      emit("run.result", {
        status: "failed",
        summary: "Workflow context was rejected.",
        error: {
          code: "LAP-201",
          message: "A valid Host-scoped workflow orchestrator context is required.",
          retryable: false,
        },
      }, "", run);
      return true;
    }
    emit("run.progress", {
      phase: "planning",
      message: "Constructed a proposal from the Host-scoped dispatch context.",
    }, "", run);
    emit("run.result", {
      status: "succeeded",
      summary: "Proposed one Host-constrained dispatch.",
      output,
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
