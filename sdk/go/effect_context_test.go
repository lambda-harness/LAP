package laplocal

import (
	"encoding/json"
	"testing"
)

func TestEffectExecutionContextParsesRules(t *testing.T) {
	r := Request{Context: json.RawMessage(`{"extensions":{"io.github.lambda-harness.lap.effect":{"version":"0.1","capability_id":"release.execute","rules":[{"effect_type":"jenkins.release","required_for_success":true,"approval_required":false,"max_intents":1}]}}}`)}
	scope, found, err := r.EffectExecutionContext()
	if err != nil || !found || scope.Rules[0].EffectType != "jenkins.release" {
		t.Fatalf("unexpected effect context: %#v %v %v", scope, found, err)
	}
}

func TestEffectExecutionContextRejectsUnorderedRules(t *testing.T) {
	r := Request{Context: json.RawMessage(`{"extensions":{"io.github.lambda-harness.lap.effect":{"version":"0.1","capability_id":"release.execute","rules":[{"effect_type":"z.effect","required_for_success":true,"approval_required":false,"max_intents":1},{"effect_type":"a.effect","required_for_success":false,"approval_required":false,"max_intents":1}]}}}`)}
	if _, _, err := r.EffectExecutionContext(); err == nil {
		t.Fatal("expected unordered rules rejection")
	}
}
