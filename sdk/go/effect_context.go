package laplocal

import (
	"bytes"
	"encoding/json"
	"fmt"
	"regexp"
)

const EffectExecutionContextExtension = "io.github.lambda-harness.lap.effect"
const EffectExecutionContextVersion = "0.1"

var effectTypePattern = regexp.MustCompile(`^[a-z][a-z0-9.-]{2,127}$`)

type EffectRule struct {
	EffectType         string `json:"effect_type"`
	RequiredForSuccess bool   `json:"required_for_success"`
	ApprovalRequired   bool   `json:"approval_required"`
	MaxIntents         int    `json:"max_intents"`
}

type EffectExecutionContext struct {
	Version      string       `json:"version"`
	CapabilityID string       `json:"capability_id"`
	Rules        []EffectRule `json:"rules"`
}

func (r Request) EffectExecutionContext() (EffectExecutionContext, bool, error) {
	trimmed := bytes.TrimSpace(r.Context)
	if len(trimmed) == 0 || bytes.Equal(trimmed, []byte("null")) {
		return EffectExecutionContext{}, false, nil
	}
	var packet struct {
		Extensions map[string]json.RawMessage `json:"extensions"`
	}
	if err := json.Unmarshal(trimmed, &packet); err != nil {
		return EffectExecutionContext{}, false, fmt.Errorf("laplocal: Context Packet is not JSON: %w", err)
	}
	raw, found := packet.Extensions[EffectExecutionContextExtension]
	if !found {
		return EffectExecutionContext{}, false, nil
	}
	var scope EffectExecutionContext
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&scope); err != nil {
		return EffectExecutionContext{}, true, fmt.Errorf("laplocal: invalid effect execution context: %w", err)
	}
	if scope.Version != EffectExecutionContextVersion || scope.CapabilityID == "" || len(scope.Rules) == 0 {
		return EffectExecutionContext{}, true, fmt.Errorf("laplocal: invalid effect execution context contract")
	}
	previous := ""
	for _, rule := range scope.Rules {
		if !effectTypePattern.MatchString(rule.EffectType) || rule.MaxIntents < 1 || rule.MaxIntents > 1000 {
			return EffectExecutionContext{}, true, fmt.Errorf("laplocal: invalid effect execution rule")
		}
		if previous != "" && rule.EffectType <= previous {
			return EffectExecutionContext{}, true, fmt.Errorf("laplocal: effect execution rules must be strictly ordered")
		}
		previous = rule.EffectType
	}
	return scope, true, nil
}
