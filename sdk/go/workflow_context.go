package laplocal

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"regexp"
)

const (
	// WorkflowOrchestratorContextExtension is the profile-owned Context Packet
	// extension that carries an external orchestrator's immutable planning view.
	WorkflowOrchestratorContextExtension = "io.github.dongrv.lap.workflow.orchestrator"
	// WorkflowOrchestratorContextVersion is the version of the extension shape.
	// It is distinct from the LAP Core version so either can evolve independently.
	WorkflowOrchestratorContextVersion = "0.1"
)

var (
	workflowAgentIDPattern    = regexp.MustCompile(`^[a-z][a-z0-9.-]{2,127}$`)
	workflowCapabilityPattern = regexp.MustCompile(`^[a-z][a-z0-9._-]{2,127}$`)
)

// WorkflowDispatchTarget is one Host-admitted target an external
// orchestrator may propose. It is a planning view, not an authorization grant.
type WorkflowDispatchTarget struct {
	AgentID      string   `json:"agent_id"`
	Capabilities []string `json:"capabilities"`
}

// WorkflowOrchestratorContext is the LAP Workflow Profile 0.1 external
// orchestrator context extension. The Host validates every returned dispatch
// separately; this context never authorizes an Agent to execute another Agent.
type WorkflowOrchestratorContext struct {
	Version           string                   `json:"version"`
	AllowedDispatches []WorkflowDispatchTarget `json:"allowed_dispatches"`
}

// WorkflowOrchestratorContext returns the optional immutable planning scope
// from this request's Context Packet. A false found result is normal for
// ordinary Agent nodes. A present extension is parsed strictly against the
// Workflow Profile so an Agent does not treat malformed scope as authority.
func (r Request) WorkflowOrchestratorContext() (WorkflowOrchestratorContext, bool, error) {
	return ParseWorkflowOrchestratorContext(r.Context)
}

// ParseWorkflowOrchestratorContext parses the optional workflow-orchestrator
// Context Packet extension. It intentionally leaves unrelated top-level
// Context Packet fields extensible while rejecting unknown fields inside this
// profile-owned extension.
func ParseWorkflowOrchestratorContext(raw json.RawMessage) (WorkflowOrchestratorContext, bool, error) {
	trimmed := bytes.TrimSpace(raw)
	if len(trimmed) == 0 || bytes.Equal(trimmed, []byte("null")) {
		return WorkflowOrchestratorContext{}, false, nil
	}

	var packet struct {
		Extensions map[string]json.RawMessage `json:"extensions"`
	}
	if err := json.Unmarshal(trimmed, &packet); err != nil {
		return WorkflowOrchestratorContext{}, false, fmt.Errorf("laplocal: Context Packet is not JSON: %w", err)
	}

	rawScope, found := packet.Extensions[WorkflowOrchestratorContextExtension]
	if !found {
		return WorkflowOrchestratorContext{}, false, nil
	}

	var scope WorkflowOrchestratorContext
	if err := decodeWorkflowOrchestratorContext(rawScope, &scope); err != nil {
		return WorkflowOrchestratorContext{}, true, fmt.Errorf("laplocal: invalid workflow orchestrator context: %w", err)
	}
	if err := validateWorkflowOrchestratorContext(scope); err != nil {
		return WorkflowOrchestratorContext{}, true, err
	}
	return scope, true, nil
}

func decodeWorkflowOrchestratorContext(raw json.RawMessage, destination *WorkflowOrchestratorContext) error {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(destination); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		if err == nil {
			return fmt.Errorf("multiple JSON values")
		}
		return err
	}
	return nil
}

func validateWorkflowOrchestratorContext(scope WorkflowOrchestratorContext) error {
	if scope.Version != WorkflowOrchestratorContextVersion {
		return fmt.Errorf("laplocal: workflow orchestrator context uses unsupported version %q", scope.Version)
	}
	if len(scope.AllowedDispatches) == 0 {
		return fmt.Errorf("laplocal: workflow orchestrator context has no allowed dispatches")
	}

	previousAgentID := ""
	for targetIndex, target := range scope.AllowedDispatches {
		if !workflowAgentIDPattern.MatchString(target.AgentID) {
			return fmt.Errorf("laplocal: workflow orchestrator context target %d has invalid agent_id", targetIndex)
		}
		if previousAgentID != "" && target.AgentID <= previousAgentID {
			return fmt.Errorf("laplocal: workflow orchestrator context target agent_id values must be strictly ordered")
		}
		previousAgentID = target.AgentID

		if len(target.Capabilities) == 0 {
			return fmt.Errorf("laplocal: workflow orchestrator context target %q has no capabilities", target.AgentID)
		}
		previousCapability := ""
		for capabilityIndex, capability := range target.Capabilities {
			if !workflowCapabilityPattern.MatchString(capability) {
				return fmt.Errorf("laplocal: workflow orchestrator context target %q capability %d is invalid", target.AgentID, capabilityIndex)
			}
			if previousCapability != "" && capability <= previousCapability {
				return fmt.Errorf("laplocal: workflow orchestrator context target %q capability values must be strictly ordered", target.AgentID)
			}
			previousCapability = capability
		}
	}

	return nil
}
