package laplocal

import (
	"encoding/json"
	"testing"
)

func TestRequestWorkflowOrchestratorContextParsesCanonicalScope(t *testing.T) {
	request := Request{Context: json.RawMessage(`{
		"extensions": {
			"io.github.lambda-harness.lap.workflow.orchestrator": {
				"version": "0.2",
				"allowed_dispatches": [
					{"agent_id": "com.example.inspector", "capabilities": ["repo.inspect"]},
					{"agent_id": "com.example.publisher", "capabilities": ["report.publish"]}
				]
			}
		}
	}`)}

	scope, found, err := request.WorkflowOrchestratorContext()
	if err != nil {
		t.Fatalf("WorkflowOrchestratorContext: %v", err)
	}
	if !found {
		t.Fatal("WorkflowOrchestratorContext did not find the extension")
	}
	if scope.Version != "0.2" {
		t.Fatalf("scope version = %q, want 0.2", scope.Version)
	}
	if len(scope.AllowedDispatches) != 2 {
		t.Fatalf("dispatch target count = %d, want 2", len(scope.AllowedDispatches))
	}
	if got := scope.AllowedDispatches[0]; got.AgentID != "com.example.inspector" || len(got.Capabilities) != 1 || got.Capabilities[0] != "repo.inspect" {
		t.Fatalf("first target = %#v", got)
	}
}

func TestRequestWorkflowOrchestratorContextTreatsAbsenceAsOptional(t *testing.T) {
	scope, found, err := (Request{Context: json.RawMessage(`{"input": {}}`)}).WorkflowOrchestratorContext()
	if err != nil {
		t.Fatalf("WorkflowOrchestratorContext: %v", err)
	}
	if found {
		t.Fatalf("found = true, scope = %#v", scope)
	}
}

func TestRequestWorkflowOrchestratorContextRejectsInvalidScope(t *testing.T) {
	for name, raw := range map[string]string{
		"unsupported-version":     `{"extensions":{"io.github.lambda-harness.lap.workflow.orchestrator":{"version":"0.1","allowed_dispatches":[{"agent_id":"com.example.inspector","capabilities":["repo.inspect"]}]}}}`,
		"empty-targets":           `{"extensions":{"io.github.lambda-harness.lap.workflow.orchestrator":{"version":"0.2","allowed_dispatches":[]}}}`,
		"unknown-extension-field": `{"extensions":{"io.github.lambda-harness.lap.workflow.orchestrator":{"version":"0.2","allowed_dispatches":[{"agent_id":"com.example.inspector","capabilities":["repo.inspect"]}],"unexpected":true}}}`,
		"unsorted-targets":        `{"extensions":{"io.github.lambda-harness.lap.workflow.orchestrator":{"version":"0.2","allowed_dispatches":[{"agent_id":"com.example.publisher","capabilities":["report.publish"]},{"agent_id":"com.example.inspector","capabilities":["repo.inspect"]}]}}}`,
		"unsorted-capabilities":   `{"extensions":{"io.github.lambda-harness.lap.workflow.orchestrator":{"version":"0.2","allowed_dispatches":[{"agent_id":"com.example.inspector","capabilities":["repo.write","repo.inspect"]}]}}}`,
		"duplicate-capability":    `{"extensions":{"io.github.lambda-harness.lap.workflow.orchestrator":{"version":"0.2","allowed_dispatches":[{"agent_id":"com.example.inspector","capabilities":["repo.inspect","repo.inspect"]}]}}}`,
	} {
		t.Run(name, func(t *testing.T) {
			_, found, err := (Request{Context: json.RawMessage(raw)}).WorkflowOrchestratorContext()
			if !found {
				t.Fatal("extension was not found")
			}
			if err == nil {
				t.Fatal("invalid extension was accepted")
			}
		})
	}
}
