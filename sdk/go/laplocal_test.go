package laplocal

import (
	"bufio"
	"context"
	"encoding/json"
	"io"
	"testing"
	"time"
)

type pipeHarness struct {
	in       *io.PipeWriter
	out      *bufio.Reader
	serveErr <-chan error
}

func startServer(t *testing.T, server *Server) pipeHarness {
	t.Helper()
	input, inputWriter := io.Pipe()
	output, outputWriter := io.Pipe()
	serveErr := make(chan error, 1)
	go func() {
		serveErr <- server.Serve(input, outputWriter)
		_ = outputWriter.Close()
	}()
	return pipeHarness{
		in: inputWriter, out: bufio.NewReader(output), serveErr: serveErr,
	}
}

func (h pipeHarness) send(t *testing.T, frame map[string]any) {
	t.Helper()
	encoded, err := json.Marshal(frame)
	if err != nil {
		t.Fatalf("marshal Host frame: %v", err)
	}
	if _, err := h.in.Write(append(encoded, '\n')); err != nil {
		t.Fatalf("write Host frame: %v", err)
	}
}

func (h pipeHarness) receive(t *testing.T) map[string]any {
	t.Helper()
	type readResult struct {
		line []byte
		err  error
	}
	result := make(chan readResult, 1)
	go func() {
		line, err := h.out.ReadBytes('\n')
		result <- readResult{line: line, err: err}
	}()
	select {
	case got := <-result:
		if got.err != nil {
			t.Fatalf("read Agent frame: %v", got.err)
		}
		var frame map[string]any
		if err := json.Unmarshal(got.line, &frame); err != nil {
			t.Fatalf("decode Agent frame: %v", err)
		}
		return frame
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for Agent frame")
		return nil
	}
}

func (h pipeHarness) close(t *testing.T) {
	t.Helper()
	if err := h.in.Close(); err != nil {
		t.Fatalf("close Host input: %v", err)
	}
	select {
	case err := <-h.serveErr:
		if err != nil {
			t.Fatalf("serve: %v", err)
		}
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for Agent shutdown")
	}
}

func (h pipeHarness) expectEOF(t *testing.T) {
	t.Helper()
	type readResult struct {
		value byte
		err   error
	}
	result := make(chan readResult, 1)
	go func() {
		value, err := h.out.ReadByte()
		result <- readResult{value: value, err: err}
	}()
	select {
	case got := <-result:
		if got.err != io.EOF {
			t.Fatalf("unexpected Agent output after shutdown: byte=%q err=%v", got.value, got.err)
		}
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for Agent output to close")
	}
}

func hostFrame(id, messageType string, run *Run, payload map[string]any) map[string]any {
	frame := map[string]any{
		"lap": "0.1", "id": id, "producer": "host.test", "seq": 1,
		"type": messageType, "payload": payload,
	}
	if run != nil {
		frame["run"] = run
	}
	return frame
}

func demoRun(id string) Run {
	return Run{
		TenantID: "tenant-test", SessionID: "session-test", RunID: id, TraceID: "trace-test",
	}
}

func newTestServer(t *testing.T, maxConcurrency int, handler Handler) *Server {
	t.Helper()
	server, err := New(Config{
		AgentID: "org.lap.sdk-test", Version: "0.1.0", MaxConcurrency: maxConcurrency,
		Capabilities: []string{"text.echo"},
	}, handler)
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	return server
}

func hello(h pipeHarness, t *testing.T) {
	t.Helper()
	h.send(t, hostFrame("host-hello", "agent.hello", nil, map[string]any{}))
	welcome := h.receive(t)
	if welcome["type"] != "agent.welcome" {
		t.Fatalf("welcome type = %v", welcome["type"])
	}
	if welcome["correlation_id"] != "host-hello" {
		t.Fatalf("welcome correlation_id = %v", welcome["correlation_id"])
	}
}

func start(h pipeHarness, t *testing.T, run Run) {
	t.Helper()
	h.send(t, hostFrame("host-start-"+run.RunID, "run.start", &run, map[string]any{
		"capability": "text.echo", "input": map[string]any{"text": run.RunID},
	}))
}

func payload(frame map[string]any) map[string]any {
	result, _ := frame["payload"].(map[string]any)
	return result
}

func TestServeRoundTripEmitsOrderedObservableEvents(t *testing.T) {
	server := newTestServer(t, 1, func(ctx context.Context, request Request, reporter Reporter) (Result, error) {
		if err := reporter.Progress("tool", "Read the requested input."); err != nil {
			return Result{}, err
		}
		if err := reporter.Artifact(Artifact{
			ID: "artifact-01", Name: "result.txt", MediaType: "text/plain",
			URI: "lap://run/output/result.txt",
		}); err != nil {
			return Result{}, err
		}
		return Succeeded("Echo complete.", map[string]any{"text": request.Run.RunID}), nil
	})
	h := startServer(t, server)
	hello(h, t)
	run := demoRun("run-roundtrip")
	start(h, t, run)

	accepted := h.receive(t)
	progress := h.receive(t)
	artifact := h.receive(t)
	result := h.receive(t)
	for index, expected := range []string{"run.accepted", "run.progress", "run.artifact", "run.result"} {
		got := []map[string]any{accepted, progress, artifact, result}[index]["type"]
		if got != expected {
			t.Fatalf("event %d type = %v, want %q", index, got, expected)
		}
	}
	if accepted["correlation_id"] != "host-start-run-roundtrip" {
		t.Fatalf("accepted correlation_id = %v", accepted["correlation_id"])
	}
	if payload(result)["status"] != "succeeded" {
		t.Fatalf("result payload = %#v", payload(result))
	}
	h.send(t, hostFrame("host-shutdown", "agent.shutdown", nil, map[string]any{}))
	h.close(t)
	h.expectEOF(t)
}

func TestRunRequiresCompletedNegotiation(t *testing.T) {
	called := false
	server := newTestServer(t, 1, func(context.Context, Request, Reporter) (Result, error) {
		called = true
		return Succeeded("unexpected", nil), nil
	})
	h := startServer(t, server)
	run := demoRun("run-before-hello")
	start(h, t, run)
	result := h.receive(t)
	if called {
		t.Fatal("handler ran before negotiation")
	}
	if payload(result)["status"] != "failed" {
		t.Fatalf("result payload = %#v", payload(result))
	}
	errorPayload, _ := payload(result)["error"].(map[string]any)
	if errorPayload["code"] != "LAP-101" {
		t.Fatalf("error payload = %#v", errorPayload)
	}
	h.send(t, hostFrame("host-shutdown", "agent.shutdown", nil, map[string]any{}))
	h.close(t)
}

func TestCancelProducesOneTerminalResult(t *testing.T) {
	started := make(chan struct{})
	server := newTestServer(t, 1, func(ctx context.Context, request Request, reporter Reporter) (Result, error) {
		close(started)
		<-ctx.Done()
		return Succeeded("handler observed cancellation", nil), nil
	})
	h := startServer(t, server)
	hello(h, t)
	run := demoRun("run-cancelled")
	start(h, t, run)
	if accepted := h.receive(t); accepted["type"] != "run.accepted" {
		t.Fatalf("accepted type = %v", accepted["type"])
	}
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("handler did not start")
	}
	h.send(t, hostFrame("host-cancel", "run.cancel", &run, map[string]any{}))
	result := h.receive(t)
	if result["type"] != "run.result" || payload(result)["status"] != "cancelled" {
		t.Fatalf("cancellation result = %#v", result)
	}
	h.send(t, hostFrame("host-shutdown", "agent.shutdown", nil, map[string]any{}))
	h.close(t)
	h.expectEOF(t)
}

func TestMaxConcurrencyRejectsSecondRun(t *testing.T) {
	started := make(chan struct{})
	server := newTestServer(t, 1, func(ctx context.Context, request Request, reporter Reporter) (Result, error) {
		close(started)
		<-ctx.Done()
		return Failed("cancelled", "Run cancelled.", "LAP-401", "Cancellation requested.", false), nil
	})
	h := startServer(t, server)
	hello(h, t)
	first := demoRun("run-first")
	start(h, t, first)
	if accepted := h.receive(t); accepted["type"] != "run.accepted" {
		t.Fatalf("accepted type = %v", accepted["type"])
	}
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("first handler did not start")
	}
	second := demoRun("run-second")
	start(h, t, second)
	rejected := h.receive(t)
	if payload(rejected)["status"] != "failed" {
		t.Fatalf("second result = %#v", rejected)
	}
	errorPayload, _ := payload(rejected)["error"].(map[string]any)
	if errorPayload["code"] != "LAP-401" {
		t.Fatalf("second error = %#v", errorPayload)
	}
	h.send(t, hostFrame("host-cancel-first", "run.cancel", &first, map[string]any{}))
	if result := h.receive(t); payload(result)["status"] != "cancelled" {
		t.Fatalf("first cancellation result = %#v", result)
	}
	h.send(t, hostFrame("host-shutdown", "agent.shutdown", nil, map[string]any{}))
	h.close(t)
}

func TestNewRejectsInvalidConfiguration(t *testing.T) {
	_, err := New(Config{AgentID: "agent", Version: "1", MaxConcurrency: -1}, func(context.Context, Request, Reporter) (Result, error) {
		return Result{}, nil
	})
	if err == nil {
		t.Fatal("New accepted negative MaxConcurrency")
	}
}

func TestArtifactValidationRejectsInvalidDescriptor(t *testing.T) {
	if _, err := normalizeArtifact(Artifact{ID: "artifact-01", Name: "report.txt", MediaType: "text/plain", URI: "relative.txt"}); err == nil {
		t.Fatal("normalizeArtifact accepted a relative URI")
	}
}

func TestInvalidTerminalArtifactBecomesTypedFailure(t *testing.T) {
	result := normalizeResult(Result{
		Status: "succeeded", Summary: "Unexpected artifact.",
		Artifacts: []Artifact{{ID: "artifact-01", Name: "report.txt", MediaType: "text/plain", URI: "relative.txt"}},
	})
	if result.Status != "failed" || result.Error == nil || result.Error.Code != "LAP-500" {
		t.Fatalf("normalized result = %#v", result)
	}
}
