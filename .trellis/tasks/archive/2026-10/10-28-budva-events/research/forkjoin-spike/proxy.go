// esWriteProxy faithfully mirrors the elasticsearchWrite node's tell contract
// (node.go tellWriteSuccess / tellWriteFailure): success -> JSON summary +
// TellSuccess; failure -> JSON failure envelope + TellFailure with a
// human-readable reason. No network: the injected delay+error lets the spike
// observe fork/join + wait + HTTP-response timing deterministically.
package main

import (
	"encoding/json"
	"fmt"
	"time"

	rulego "github.com/rulego/rulego"
	"github.com/rulego/rulego/api/types"
)

// RegisterProxyNode installs the proxy on the default component registry.
// Idempotent: re-registration returns false.
func RegisterProxyNode() bool {
	err := rulego.Registry.Register(&esWriteProxy{})
	return err == nil
}

type esWriteProxy struct {
	fail  bool
	delay time.Duration
}

func (*esWriteProxy) Type() string { return "esWriteProxy" }
func (*esWriteProxy) New() types.Node {
	return &esWriteProxy{}
}
func (n *esWriteProxy) Init(_ types.Config, configuration types.Configuration) error {
	n.fail = false
	n.delay = 0
	if v, ok := configuration["fail"].(bool); ok {
		n.fail = v
	}
	if v, ok := configuration["delayMs"].(float64); ok {
		n.delay = time.Duration(v) * time.Millisecond
	}
	return nil
}
func (*esWriteProxy) Destroy() {}

// OnMsg reproduces the real node's two tell paths.
func (n *esWriteProxy) OnMsg(ctx types.RuleContext, msg types.RuleMsg) {
	if n.delay > 0 {
		select {
		case <-time.After(n.delay):
		case <-ctx.GetContext().Done():
			ctx.TellFailure(msg, fmt.Errorf("esWriteProxy: cancelled"))
			return
		}
	}
	out := msg.Copy()
	out.DataType = types.JSON
	if n.fail {
		b, _ := json.Marshal(map[string]interface{}{
			"classification": "terminal",
			"reason":         "esWriteProxy: injected bulk item status 503 on index probe",
		})
		out.SetBytes(b)
		ctx.TellFailure(out, fmt.Errorf("esWriteProxy: injected bulk item status 503 on index probe"))
		return
	}
	b, _ := json.Marshal(map[string]interface{}{
		"accepted": 1, "duplicates": 0, "total": 1,
		"results": []map[string]interface{}{{"status": 201, "op": "index", "class": "ok"}},
	})
	out.SetBytes(b)
	ctx.TellSuccess(out)
}
