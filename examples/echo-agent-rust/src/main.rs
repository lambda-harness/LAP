use serde_json::{json, Value};
use std::io::{self, BufRead, Write};

const AGENT_ID: &str = "org.lap.rust-echo-agent";
const VERSION: &str = "0.1.0";

fn emit<W: Write>(
    writer: &mut W,
    sequence: &mut u64,
    message_type: &str,
    payload: Value,
    correlation_id: Option<&str>,
    run: Option<&Value>,
) -> io::Result<()> {
    *sequence += 1;
    let mut frame = json!({
        "lap": "0.1",
        "id": format!("rust-echo-{}", *sequence),
        "producer": AGENT_ID,
        "seq": *sequence,
        "type": message_type,
        "payload": payload,
    });
    let object = frame.as_object_mut().expect("protocol frame is an object");
    if let Some(value) = correlation_id {
        object.insert("correlation_id".into(), Value::String(value.into()));
    }
    if let Some(value) = run {
        object.insert("run".into(), value.clone());
    }
    serde_json::to_writer(&mut *writer, &frame).map_err(io::Error::other)?;
    writer.write_all(b"\n")?;
    writer.flush()
}

fn handle<W: Write>(frame: &Value, writer: &mut W, sequence: &mut u64) -> io::Result<bool> {
    let message_type = frame.get("type").and_then(Value::as_str).unwrap_or("");
    let run = frame.get("run");
    match message_type {
        "agent.hello" => {
            emit(
                writer,
                sequence,
                "agent.welcome",
                json!({
                    "selected_lap": "0.1",
                    "profiles": ["lap-local/0.1"],
                    "agent_id": AGENT_ID,
                    "version": VERSION,
                    "max_concurrency": 1,
                }),
                frame.get("id").and_then(Value::as_str),
                None,
            )?;
            Ok(true)
        }
        "run.start" => {
            let capability = frame
                .pointer("/payload/capability")
                .cloned()
                .unwrap_or(Value::Null);
            let text = frame
                .pointer("/payload/input/text")
                .and_then(Value::as_str)
                .unwrap_or("");
            emit(
                writer,
                sequence,
                "run.accepted",
                json!({"capability": capability}),
                frame.get("id").and_then(Value::as_str),
                run,
            )?;
            emit(
                writer,
                sequence,
                "run.progress",
                json!({"phase": "agent", "message": "Echoing input."}),
                None,
                run,
            )?;
            emit(
                writer,
                sequence,
                "run.result",
                json!({
                    "status": "succeeded",
                    "summary": "Echo complete.",
                    "output": {"text": text},
                }),
                None,
                run,
            )?;
            Ok(true)
        }
        "run.cancel" => {
            emit(
                writer,
                sequence,
                "run.result",
                json!({
                    "status": "cancelled",
                    "summary": "Run cancelled.",
                    "error": {
                        "code": "LAP-401",
                        "message": "Cancellation requested.",
                        "retryable": false,
                    },
                }),
                None,
                run,
            )?;
            Ok(true)
        }
        "agent.shutdown" => Ok(false),
        _ => Ok(true),
    }
}

fn run() -> Result<(), String> {
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut output = stdout.lock();
    let mut sequence = 0;

    for raw in stdin.lock().lines() {
        let raw = raw.map_err(|error| error.to_string())?;
        let frame: Value = serde_json::from_str(&raw).map_err(|error| error.to_string())?;
        if !frame.is_object() {
            return Err("LAP frame must be a JSON object".into());
        }
        if !handle(&frame, &mut output, &mut sequence).map_err(|error| error.to_string())? {
            break;
        }
    }
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(2);
    }
}
