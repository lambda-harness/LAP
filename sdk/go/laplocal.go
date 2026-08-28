// Package laplocal implements the Agent-side LAP Local 0.1 stdio loop.
//
// It is a small reference SDK, not a Host runtime.  The Host continues to own
// authentication, tenant identity, package activation, authorization, limits,
// process supervision, and durable terminal state.
package laplocal

import (
	"bufio"
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/url"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const (
	// Version is the LAP Core version implemented by this SDK.
	Version = "0.1"
	// Profile is the LAP Local stdio profile implemented by this SDK.
	Profile = "lap-local/0.1"
	// WorkflowProfile is the optional LAP Workflow profile used by a local
	// Agent that can safely consume the Host-scoped orchestrator context.
	WorkflowProfile = "lap-workflow/0.1"
)

var (
	// ErrRunClosed means the Host cancelled or completed the run before the
	// handler attempted to report more non-terminal work.
	ErrRunClosed = errors.New("laplocal: run is already terminal")
)

// Config identifies one Agent process and bounds its local protocol loop.
// MaxConcurrency must agree with the package manifest the Host activated.
type Config struct {
	AgentID         string
	Version         string
	MaxConcurrency  int
	MaxFrameBytes   int
	ShutdownTimeout time.Duration
	Capabilities    []string
	// AdditionalProfiles declares optional LAP profiles this Agent supports.
	// Profile is always advertised automatically. A Host remains responsible
	// for requesting and requiring an optional profile before it sends any
	// profile-specific Context Packet extension.
	AdditionalProfiles []string
}

// Run is the immutable Host-provided identity for one request.
type Run struct {
	TenantID    string `json:"tenant_id"`
	SessionID   string `json:"session_id"`
	RunID       string `json:"run_id"`
	ParentRunID string `json:"parent_run_id,omitempty"`
	TraceID     string `json:"trace_id"`
}

// Request is the Agent-visible portion of a validated run.start frame.
// Input and Context remain JSON so an Agent can preserve its declared
// capability contract without a lossy text conversion.
type Request struct {
	Run            Run
	Capability     string
	Input          json.RawMessage
	Context        json.RawMessage
	IdempotencyKey string
}

// Failure describes a typed non-success terminal result.
type Failure struct {
	Code      string `json:"code"`
	Message   string `json:"message"`
	Retryable bool   `json:"retryable,omitempty"`
}

// Artifact is an immutable output-artifact reference. The Host remains
// responsible for granting access and validating a result against its full
// capability contract.
type Artifact struct {
	ID        string `json:"id"`
	Name      string `json:"name"`
	MediaType string `json:"media_type"`
	URI       string `json:"uri,omitempty"`
	SizeBytes *int64 `json:"size_bytes,omitempty"`
	SHA256    string `json:"sha256,omitempty"`
}

// Result is the one terminal value returned by a Handler.
type Result struct {
	Status    string
	Summary   string
	Output    any
	Artifacts []Artifact
	Error     *Failure
}

// Succeeded builds a successful terminal result.
func Succeeded(summary string, output any) Result {
	return Result{Status: "succeeded", Summary: summary, Output: output}
}

// Failed builds a typed non-success terminal result.
func Failed(status, summary, code, message string, retryable bool) Result {
	return Result{
		Status:  status,
		Summary: summary,
		Error:   &Failure{Code: code, Message: message, Retryable: retryable},
	}
}

// Reporter exposes only observable, run-scoped Agent output. It deliberately
// has no API for Host credentials, paths, grants, or hidden model reasoning.
type Reporter interface {
	Progress(phase, message string) error
	Artifact(artifact Artifact) error
}

// Handler performs one capability invocation. It must return when ctx is
// cancelled. A returned error is converted to a typed LAP-500 result without
// leaking the implementation error text to the protocol stream.
type Handler func(ctx context.Context, request Request, reporter Reporter) (Result, error)

type envelope struct {
	LAP            string          `json:"lap"`
	ID             string          `json:"id"`
	CorrelationID  string          `json:"correlation_id,omitempty"`
	Producer       string          `json:"producer"`
	Sequence       uint64          `json:"seq"`
	Type           string          `json:"type"`
	Run            *Run            `json:"run,omitempty"`
	IdempotencyKey string          `json:"idempotency_key,omitempty"`
	Payload        json.RawMessage `json:"payload"`
}

type activeRun struct {
	request Request
	cancel  context.CancelFunc

	mu       sync.Mutex
	terminal bool
}

// Server owns one local Agent process protocol loop. It is safe for a Handler
// and the stdin reader to emit concurrently; stdout frames remain ordered with
// a single strictly increasing producer sequence.
type Server struct {
	config  Config
	handler Handler

	writeMu sync.Mutex
	writer  *bufio.Writer
	seq     atomic.Uint64

	activeMu   sync.Mutex
	active     map[string]*activeRun
	negotiated bool
	closing    bool
	wg         sync.WaitGroup
}

// New validates an Agent-side configuration. The Host still validates the
// manifest before it launches this process.
func New(config Config, handler Handler) (*Server, error) {
	if strings.TrimSpace(config.AgentID) == "" {
		return nil, errors.New("laplocal: AgentID is required")
	}
	if strings.TrimSpace(config.Version) == "" {
		return nil, errors.New("laplocal: Version is required")
	}
	if handler == nil {
		return nil, errors.New("laplocal: Handler is required")
	}
	if config.MaxConcurrency == 0 {
		config.MaxConcurrency = 1
	}
	if config.MaxConcurrency < 1 {
		return nil, errors.New("laplocal: MaxConcurrency must be positive")
	}
	if config.MaxFrameBytes == 0 {
		config.MaxFrameBytes = 1024 * 1024
	}
	if config.MaxFrameBytes < 1024 {
		return nil, errors.New("laplocal: MaxFrameBytes must be at least 1024")
	}
	if config.ShutdownTimeout == 0 {
		config.ShutdownTimeout = 10 * time.Second
	}
	if config.ShutdownTimeout < 0 {
		return nil, errors.New("laplocal: ShutdownTimeout must not be negative")
	}
	config.AgentID = strings.TrimSpace(config.AgentID)
	config.Version = strings.TrimSpace(config.Version)
	profiles, err := normalizeAdditionalProfiles(config.AdditionalProfiles)
	if err != nil {
		return nil, err
	}
	config.AdditionalProfiles = profiles
	return &Server{config: config, handler: handler, active: make(map[string]*activeRun)}, nil
}

// Serve processes UTF-8 JSON Lines from input and writes only protocol frames
// to output. Diagnostics are returned to the caller so the Agent executable
// can decide how to write them to stderr.
func (s *Server) Serve(input io.Reader, output io.Writer) error {
	if input == nil || output == nil {
		return errors.New("laplocal: input and output are required")
	}
	s.writeMu.Lock()
	if s.writer != nil {
		s.writeMu.Unlock()
		return errors.New("laplocal: Server.Serve may only be called once")
	}
	s.writer = bufio.NewWriter(output)
	s.writeMu.Unlock()

	scanner := bufio.NewScanner(input)
	scanner.Buffer(make([]byte, 4096), s.config.MaxFrameBytes+1)
	for scanner.Scan() {
		if len(scanner.Bytes()) > s.config.MaxFrameBytes {
			return errors.New("laplocal: Host sent an oversized protocol frame")
		}
		var frame envelope
		if err := json.Unmarshal(scanner.Bytes(), &frame); err != nil {
			return fmt.Errorf("laplocal: Host frame is not valid JSON: %w", err)
		}
		if err := s.handle(frame); err != nil {
			return err
		}
		if frame.Type == "agent.shutdown" {
			return s.shutdown()
		}
	}
	if err := scanner.Err(); err != nil {
		return fmt.Errorf("laplocal: unable to read Host protocol stream: %w", err)
	}
	return s.shutdown()
}

func (s *Server) handle(frame envelope) error {
	if frame.LAP != Version {
		return fmt.Errorf("laplocal: unsupported LAP version %q", frame.LAP)
	}
	if strings.TrimSpace(frame.ID) == "" || strings.TrimSpace(frame.Producer) == "" {
		return errors.New("laplocal: Host frame is missing id or producer")
	}
	switch frame.Type {
	case "agent.hello":
		return s.welcome(frame)
	case "run.start":
		return s.startRun(frame)
	case "run.cancel":
		return s.cancelRun(frame)
	case "agent.shutdown":
		s.activeMu.Lock()
		s.closing = true
		s.activeMu.Unlock()
		return nil
	default:
		return fmt.Errorf("laplocal: Host sent unsupported message type %q", frame.Type)
	}
}

func (s *Server) welcome(frame envelope) error {
	var payload struct {
		SupportedLAP []string `json:"supported_lap"`
		Profiles     []string `json:"profiles"`
	}
	if err := json.Unmarshal(frame.Payload, &payload); err != nil {
		return errors.New("laplocal: agent.hello payload must be an object")
	}
	// Earlier Core 0.1 examples use an empty object here. A Host that does
	// advertise alternatives must include this supported version and profile.
	if len(payload.SupportedLAP) > 0 && !contains(payload.SupportedLAP, Version) {
		return errors.New("laplocal: Host did not offer LAP 0.1")
	}
	if len(payload.Profiles) > 0 && !contains(payload.Profiles, Profile) {
		return errors.New("laplocal: Host did not offer LAP Local 0.1")
	}
	if err := s.emit("agent.welcome", map[string]any{
		"selected_lap":    Version,
		"profiles":        s.supportedProfiles(),
		"agent_id":        s.config.AgentID,
		"version":         s.config.Version,
		"max_concurrency": s.config.MaxConcurrency,
	}, frame.ID, nil); err != nil {
		return err
	}
	s.activeMu.Lock()
	s.negotiated = true
	s.activeMu.Unlock()
	return nil
}

func (s *Server) supportedProfiles() []string {
	profiles := make([]string, 1, len(s.config.AdditionalProfiles)+1)
	profiles[0] = Profile
	profiles = append(profiles, s.config.AdditionalProfiles...)
	return profiles
}

func normalizeAdditionalProfiles(raw []string) ([]string, error) {
	seen := make(map[string]struct{}, len(raw))
	profiles := make([]string, 0, len(raw))
	for _, value := range raw {
		profile := strings.TrimSpace(value)
		if profile == "" {
			return nil, errors.New("laplocal: AdditionalProfiles must not contain an empty profile")
		}
		if profile == Profile {
			return nil, errors.New("laplocal: AdditionalProfiles must not repeat lap-local/0.1")
		}
		if _, exists := seen[profile]; exists {
			return nil, fmt.Errorf("laplocal: AdditionalProfiles contains duplicate profile %q", profile)
		}
		seen[profile] = struct{}{}
		profiles = append(profiles, profile)
	}
	sort.Strings(profiles)
	return profiles, nil
}

func (s *Server) startRun(frame envelope) error {
	if frame.Run == nil || !validRun(*frame.Run) {
		return errors.New("laplocal: run.start is missing a complete run identity")
	}
	var payload struct {
		Capability string          `json:"capability"`
		Input      json.RawMessage `json:"input"`
		Context    json.RawMessage `json:"context"`
	}
	if err := json.Unmarshal(frame.Payload, &payload); err != nil {
		return errors.New("laplocal: run.start payload must be an object")
	}
	payload.Capability = strings.TrimSpace(payload.Capability)
	if payload.Capability == "" {
		return errors.New("laplocal: run.start payload is missing capability")
	}
	if len(payload.Input) == 0 {
		payload.Input = json.RawMessage("null")
	}
	if len(payload.Context) == 0 {
		payload.Context = json.RawMessage("{}")
	}
	request := Request{
		Run:            *frame.Run,
		Capability:     payload.Capability,
		Input:          append(json.RawMessage(nil), payload.Input...),
		Context:        append(json.RawMessage(nil), payload.Context...),
		IdempotencyKey: frame.IdempotencyKey,
	}

	s.activeMu.Lock()
	if !s.negotiated {
		s.activeMu.Unlock()
		return s.reject(request.Run, "LAP-101", "Agent negotiation has not completed.")
	}
	if s.closing {
		s.activeMu.Unlock()
		return s.reject(request.Run, "LAP-401", "Agent is shutting down and cannot accept a new run.")
	}
	if len(s.config.Capabilities) > 0 && !contains(s.config.Capabilities, request.Capability) {
		s.activeMu.Unlock()
		return s.reject(request.Run, "LAP-201", "The requested capability is not implemented by this Agent.")
	}
	if _, exists := s.active[request.Run.RunID]; exists {
		s.activeMu.Unlock()
		return s.reject(request.Run, "LAP-201", "A run with this run_id is already active.")
	}
	if len(s.active) >= s.config.MaxConcurrency {
		s.activeMu.Unlock()
		return s.reject(request.Run, "LAP-401", "Agent has reached its declared maximum concurrency.")
	}
	ctx, cancel := context.WithCancel(context.Background())
	run := &activeRun{request: request, cancel: cancel}
	s.active[request.Run.RunID] = run
	s.activeMu.Unlock()

	if err := s.emit("run.accepted", map[string]any{"capability": request.Capability}, frame.ID, &request.Run); err != nil {
		s.removeRun(request.Run.RunID, run)
		cancel()
		return err
	}
	s.wg.Add(1)
	go s.execute(ctx, run)
	return nil
}

func (s *Server) execute(ctx context.Context, run *activeRun) {
	defer s.wg.Done()
	if ctx.Err() != nil {
		return
	}
	result, err := s.handler(ctx, run.request, runReporter{server: s, run: run})
	if err != nil {
		result = Failed("failed", "Agent handler failed.", "LAP-500", "Agent handler returned an error.", false)
	}
	_, _ = s.terminal(run, normalizeResult(result))
}

func (s *Server) cancelRun(frame envelope) error {
	if frame.Run == nil || strings.TrimSpace(frame.Run.RunID) == "" {
		return errors.New("laplocal: run.cancel is missing run_id")
	}
	s.activeMu.Lock()
	run := s.active[frame.Run.RunID]
	s.activeMu.Unlock()
	if run == nil {
		return nil // A completed run is immutable; cancellation is idempotent.
	}
	_, err := s.terminal(run, Failed(
		"cancelled", "Run cancelled.", "LAP-401", "Cancellation requested by the Host.", false,
	))
	return err
}

func (s *Server) reject(run Run, code, message string) error {
	return s.emit("run.result", resultPayload(Failed(
		"failed", "Run rejected.", code, message, true,
	)), "", &run)
}

func (s *Server) terminal(run *activeRun, result Result) (bool, error) {
	run.mu.Lock()
	defer run.mu.Unlock()
	if run.terminal {
		return false, nil
	}
	run.terminal = true
	run.cancel()
	err := s.emit("run.result", resultPayload(result), "", &run.request.Run)
	s.removeRun(run.request.Run.RunID, run)
	return true, err
}

func (s *Server) removeRun(runID string, target *activeRun) {
	s.activeMu.Lock()
	if s.active[runID] == target {
		delete(s.active, runID)
	}
	s.activeMu.Unlock()
}

func (s *Server) shutdown() error {
	s.activeMu.Lock()
	s.closing = true
	pending := len(s.active)
	s.activeMu.Unlock()
	if pending == 0 {
		return nil
	}
	done := make(chan struct{})
	go func() {
		s.wg.Wait()
		close(done)
	}()
	select {
	case <-done:
		return nil
	case <-time.After(s.config.ShutdownTimeout):
		s.cancelAll("Agent shutdown exceeded its grace period.")
		return nil
	}
}

func (s *Server) cancelAll(reason string) {
	s.activeMu.Lock()
	runs := make([]*activeRun, 0, len(s.active))
	for _, run := range s.active {
		runs = append(runs, run)
	}
	s.activeMu.Unlock()
	for _, run := range runs {
		_, _ = s.terminal(run, Failed(
			"cancelled", "Agent is shutting down.", "LAP-401", reason, false,
		))
	}
}

func (s *Server) emit(messageType string, payload any, correlationID string, run *Run) error {
	s.writeMu.Lock()
	defer s.writeMu.Unlock()
	if s.writer == nil {
		return errors.New("laplocal: Server is not serving")
	}
	sequence := s.seq.Add(1)
	frame := map[string]any{
		"lap":      Version,
		"id":       fmt.Sprintf("%s-%d", s.config.AgentID, sequence),
		"producer": s.config.AgentID,
		"seq":      sequence,
		"type":     messageType,
		"payload":  payload,
	}
	if correlationID != "" {
		frame["correlation_id"] = correlationID
	}
	if run != nil {
		frame["run"] = run
	}
	if err := json.NewEncoder(s.writer).Encode(frame); err != nil {
		return fmt.Errorf("laplocal: unable to write protocol frame: %w", err)
	}
	return s.writer.Flush()
}

type runReporter struct {
	server *Server
	run    *activeRun
}

func (r runReporter) Progress(phase, message string) error {
	phase = strings.TrimSpace(phase)
	message = strings.TrimSpace(message)
	if phase == "" || message == "" {
		return errors.New("laplocal: progress requires phase and message")
	}
	return r.emit("run.progress", map[string]any{"phase": phase, "message": message})
}

func (r runReporter) Artifact(artifact Artifact) error {
	artifact, err := normalizeArtifact(artifact)
	if err != nil {
		return err
	}
	return r.emit("run.artifact", artifact)
}

func (r runReporter) emit(messageType string, payload any) error {
	r.run.mu.Lock()
	defer r.run.mu.Unlock()
	if r.run.terminal {
		return ErrRunClosed
	}
	return r.server.emit(messageType, payload, "", &r.run.request.Run)
}

func normalizeArtifact(artifact Artifact) (Artifact, error) {
	artifact.ID = strings.TrimSpace(artifact.ID)
	artifact.Name = strings.TrimSpace(artifact.Name)
	artifact.MediaType = strings.TrimSpace(artifact.MediaType)
	artifact.URI = strings.TrimSpace(artifact.URI)
	artifact.SHA256 = strings.TrimSpace(artifact.SHA256)
	if artifact.ID == "" || artifact.Name == "" || artifact.MediaType == "" {
		return Artifact{}, errors.New("laplocal: artifact requires id, name, and media_type")
	}
	if artifact.SizeBytes != nil && *artifact.SizeBytes < 0 {
		return Artifact{}, errors.New("laplocal: artifact size_bytes must not be negative")
	}
	if artifact.URI != "" {
		parsed, err := url.ParseRequestURI(artifact.URI)
		if err != nil || !parsed.IsAbs() {
			return Artifact{}, errors.New("laplocal: artifact uri must be an absolute URI")
		}
	}
	if artifact.SHA256 != "" {
		if len(artifact.SHA256) != 64 {
			return Artifact{}, errors.New("laplocal: artifact sha256 must contain 64 hexadecimal characters")
		}
		if _, err := hex.DecodeString(artifact.SHA256); err != nil {
			return Artifact{}, errors.New("laplocal: artifact sha256 must contain 64 hexadecimal characters")
		}
	}
	return artifact, nil
}

func normalizeResult(result Result) Result {
	for index, artifact := range result.Artifacts {
		normalized, err := normalizeArtifact(artifact)
		if err != nil {
			return Failed("failed", "Agent returned an invalid artifact.", "LAP-500", "Agent returned an invalid artifact descriptor.", false)
		}
		result.Artifacts[index] = normalized
	}
	result.Status = strings.TrimSpace(result.Status)
	switch result.Status {
	case "succeeded", "failed", "cancelled", "timed_out":
	default:
		result.Status = "failed"
		result.Error = &Failure{Code: "LAP-500", Message: "Agent handler returned an invalid terminal status."}
	}
	result.Summary = strings.TrimSpace(result.Summary)
	if result.Summary == "" {
		if result.Status == "succeeded" {
			result.Summary = "Agent completed the requested task."
		} else {
			result.Summary = "Agent did not complete the requested task."
		}
	}
	if result.Status == "succeeded" {
		result.Error = nil
		return result
	}
	if result.Error == nil {
		result.Error = &Failure{Code: "LAP-500", Message: result.Summary}
	}
	if strings.TrimSpace(result.Error.Code) == "" {
		result.Error.Code = "LAP-500"
	}
	if strings.TrimSpace(result.Error.Message) == "" {
		result.Error.Message = result.Summary
	}
	return result
}

func resultPayload(result Result) map[string]any {
	payload := map[string]any{
		"status":  result.Status,
		"summary": result.Summary,
	}
	if result.Status == "succeeded" {
		payload["output"] = result.Output
	} else if result.Error != nil {
		payload["error"] = result.Error
	}
	if len(result.Artifacts) > 0 {
		payload["artifacts"] = result.Artifacts
	}
	return payload
}

func validRun(run Run) bool {
	return strings.TrimSpace(run.TenantID) != "" && strings.TrimSpace(run.SessionID) != "" &&
		strings.TrimSpace(run.RunID) != "" && strings.TrimSpace(run.TraceID) != ""
}

func contains(values []string, expected string) bool {
	for _, value := range values {
		if value == expected {
			return true
		}
	}
	return false
}
