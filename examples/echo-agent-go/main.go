// LAP Local 0.1 Go reference Agent. Stdout contains protocol frames only.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"

	laplocal "github.com/dongrv/LAP/sdk/go"
)

type input struct {
	Text string `json:"text"`
}

func main() {
	server, err := laplocal.New(laplocal.Config{
		AgentID: "org.lap.go-echo-agent", Version: "0.1.0", MaxConcurrency: 1,
		Capabilities: []string{"text.echo"},
	}, func(ctx context.Context, request laplocal.Request, reporter laplocal.Reporter) (laplocal.Result, error) {
		var payload input
		if err := json.Unmarshal(request.Input, &payload); err != nil {
			return laplocal.Failed("failed", "Echo input is invalid.", "LAP-201", "Expected an input object with text.", false), nil
		}
		if err := reporter.Progress("agent", "Echoing input."); err != nil {
			return laplocal.Result{}, err
		}
		return laplocal.Succeeded("Echo complete.", map[string]any{"text": payload.Text}), nil
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	if err := server.Serve(os.Stdin, os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
}
