// LAP Local 0.1 Go external orchestrator. Stdout contains protocol frames only.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"

	laplocal "github.com/lambda-harness/LAP/sdk/go"
)

const (
	agentID    = "org.lap.go-orchestrator-agent"
	capability = "plan.dispatch"
)

func main() {
	server, err := laplocal.New(laplocal.Config{
		AgentID:            agentID,
		Version:            "0.1.0",
		MaxConcurrency:     1,
		Capabilities:       []string{capability},
		AdditionalProfiles: []string{laplocal.WorkflowProfile},
	}, planDispatch)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	if err := server.Serve(os.Stdin, os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
}

func planDispatch(_ context.Context, request laplocal.Request, reporter laplocal.Reporter) (laplocal.Result, error) {
	scope, found, err := request.WorkflowOrchestratorContext()
	if err != nil || !found {
		return laplocal.Failed(
			"failed",
			"Workflow context was rejected.",
			"LAP-201",
			"A valid Host-scoped workflow orchestrator context is required.",
			false,
		), nil
	}

	target := scope.AllowedDispatches[0]
	if err := reporter.Progress("planning", "Constructed a proposal from the Host-scoped dispatch context."); err != nil {
		return laplocal.Result{}, err
	}
	return laplocal.Succeeded("Proposed one Host-constrained dispatch.", map[string]any{
		"dispatch": []map[string]any{{
			"agent_id":   target.AgentID,
			"capability": target.Capabilities[0],
			"input":      json.RawMessage(request.Input),
		}},
	}), nil
}
