// Harness for the Budva example profile.
//
// This test is the mechanical boundary proof for examples/budva: it runs the
// deployed jsTransform script (crypto.js + parser.js, exactly as chain.json
// embeds it) through the SAME engine the deployed jsTransform node uses —
// rulego v1.0.0's GojaJsEngine, the node's JsTransformFuncTemplate wrapper —
// so a green test means the committed JS is the JS that runs in the chain.
// External anchors: RFC 6234 digests, a Go-stdlib HMAC reference (independent
// implementation), and the elasticsearchWrite plugin's message contract. It
// imports rulego (the engine) but never the plugin package.
package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/rulego/rulego/api/types"
	"github.com/rulego/rulego/components/transform"
	"github.com/rulego/rulego/utils/js"
)

// RFC 6234 digests — the well-known external constants.
const (
	sha256Empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
	sha256ABC   = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
	// RFC 4231 test case 2 input; the digest is computed by Go's crypto/hmac at
	// test time (independent reference implementation) rather than memorized.
	jefeKey  = "Jefe"
	jefeData = "what do ya want for nothing?"
)

// buildEngine reproduces jsTransform's node wiring (js_transform_node.go Init):
// NewGojaJsEngine(config, fmt.Sprintf(JsTransformFuncTemplate, jsScript), vars).
func buildEngine(t *testing.T, jsScript string, props map[string]string) *js.GojaJsEngine {
	t.Helper()
	config := types.NewConfig()
	for k, v := range props {
		config.Properties.PutValue(k, v)
	}
	engine, err := js.NewGojaJsEngine(config, strings.Replace(transform.JsTransformFuncTemplate, "%s", jsScript, 1), nil)
	if err != nil {
		t.Fatalf("NewGojaJsEngine: %v", err)
	}
	return engine
}

func runTransform(t *testing.T, engine *js.GojaJsEngine, msg string, metadata map[string]string, msgType string) (map[string]interface{}, error) {
	t.Helper()
	out, err := engine.Execute(nil, transform.JsTransformFuncName, msg, metadata, msgType, "TEXT")
	if err != nil {
		return nil, err
	}
	m, ok := out.(map[string]interface{})
	if !ok {
		return nil, fmt.Errorf("transform returned %T, want map", out)
	}
	return m, nil
}

func readAsset(t *testing.T, name string) string {
	t.Helper()
	b, err := os.ReadFile(name)
	if err != nil {
		t.Fatalf("read %s: %v", name, err)
	}
	return string(b)
}

func mustRead(t *testing.T, path string) []byte {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return b
}

// parseScript is exactly what chain.json embeds in the parse node.
func parseScript(t *testing.T) string {
	t.Helper()
	return readAsset(t, "crypto.js") + "\n" + readAsset(t, "parser.js")
}

// eventsScript is exactly what chain.json embeds in the audit node.
func eventsScript(t *testing.T) string {
	t.Helper()
	return readAsset(t, "crypto.js") + "\n" + readAsset(t, "events.js")
}

// parseOutput runs the committed parse script and returns the messages
// contract (as the object the next jsTransform receives for a JSON data
// type, components/base base.go GetDataByType) plus the stamped metadata,
// normalized to map[string]string (the type the engine writes back via
// processJsResult ReplaceAll). The goja engine hands the returned metadata
// back as either map[string]string or map[string]interface{} depending on
// how the script touched it; both are normalized here.
func parseOutput(t *testing.T, raw []byte, meta map[string]string) (interface{}, map[string]string) {
	t.Helper()
	engine := buildEngine(t, parseScript(t), map[string]string{"budva_hmac_key": ""})
	out, err := runTransform(t, engine, hexOf(raw), meta, "budva-to-es")
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	var contract interface{}
	if err := json.Unmarshal([]byte(out["msg"].(string)), &contract); err != nil {
		t.Fatalf("parse emit not JSON: %v", err)
	}
	return contract, normalizeMetadata(t, out["metadata"])
}

func normalizeMetadata(t *testing.T, v interface{}) map[string]string {
	t.Helper()
	m := make(map[string]string)
	switch mm := v.(type) {
	case map[string]string:
		for k, val := range mm {
			m[k] = val
		}
	case map[string]interface{}:
		for k, val := range mm {
			m[k] = fmt.Sprintf("%v", val)
		}
	default:
		t.Fatalf("metadata came back as %T, want a string map", v)
	}
	return m
}

func hexOf(raw []byte) string { return strings.ToUpper(hex.EncodeToString(raw)) }

func sign(key string, raw []byte) string {
	mac := hmac.New(sha256.New, []byte(key))
	mac.Write(raw)
	return "sha256=" + hex.EncodeToString(mac.Sum(nil))
}

// TestCryptoVectors pins the vendored crypto against external facts under the
// real goja engine: RFC 6234 digests, a Go-stdlib HMAC reference, the 64/65-
// byte key path (RFC 2104 §3), and a UTF-8 round-trip through the exact
// hexToBytes+utf8Decode path the parser uses for the raw body.
func TestCryptoVectors(t *testing.T) {
	crypto := readAsset(t, "crypto.js")
	probe := `
		var kb = utf8Encode('Jefe');
		var mb = utf8Encode('what do ya want for nothing?');
		var kb64 = new Array(64); for (var i = 0; i < 64; i++) kb64[i] = 0x61;
		var kb65 = new Array(65); for (var i = 0; i < 65; i++) kb65[i] = 0x61;
		var sample = 'héllo ☃ budva-测试';
		var sb = utf8Encode(sample);
		var back = utf8Decode(hexToBytes(bytesToHex(sb)));
		return { msg: JSON.stringify({
			sha256_empty: bytesToHex(sha256Bytes([])),
			sha256_abc:   bytesToHex(sha256Bytes(utf8Encode('abc'))),
			hmac_jefe:    bytesToHex(hmacSha256Bytes(kb, mb)),
			hmac_64:      bytesToHex(hmacSha256Bytes(kb64, utf8Encode('x'))),
			hmac_65:      bytesToHex(hmacSha256Bytes(kb65, utf8Encode('x'))),
			utf8_ok:      back === sample
		}), metadata: metadata, msgType: msgType };`
	engine := buildEngine(t, crypto+"\n"+probe, nil)
	out, err := runTransform(t, engine, "00", map[string]string{}, "T")
	if err != nil {
		t.Fatalf("run: %v", err)
	}
	var got struct {
		Sha256Empty string `json:"sha256_empty"`
		Sha256ABC   string `json:"sha256_abc"`
		HmacJefe    string `json:"hmac_jefe"`
		Hmac64      string `json:"hmac_64"`
		Hmac65      string `json:"hmac_65"`
		Utf8OK      bool   `json:"utf8_ok"`
	}
	if err := json.Unmarshal([]byte(out["msg"].(string)), &got); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if got.Sha256Empty != sha256Empty {
		t.Errorf("sha256_empty = %s, want %s", got.Sha256Empty, sha256Empty)
	}
	if got.Sha256ABC != sha256ABC {
		t.Errorf("sha256_abc = %s, want %s", got.Sha256ABC, sha256ABC)
	}
	mac := hmac.New(sha256.New, []byte(jefeKey))
	mac.Write([]byte(jefeData))
	if wantJefe := hex.EncodeToString(mac.Sum(nil)); got.HmacJefe != wantJefe {
		t.Errorf("hmac_jefe = %s, want (Go reference) %s", got.HmacJefe, wantJefe)
	}
	k64 := make([]byte, 64)
	for i := range k64 {
		k64[i] = 0x61
	}
	k65 := make([]byte, 65)
	for i := range k65 {
		k65[i] = 0x61
	}
	want64 := hmac.New(sha256.New, k64)
	want64.Write([]byte("x"))
	want65 := hmac.New(sha256.New, k65)
	want65.Write([]byte("x"))
	if got.Hmac64 != hex.EncodeToString(want64.Sum(nil)) {
		t.Errorf("hmac_64 (64-byte key path) mismatch")
	}
	if got.Hmac65 != hex.EncodeToString(want65.Sum(nil)) {
		t.Errorf("hmac_65 (hashed-key path) mismatch")
	}
	if !got.Utf8OK {
		t.Errorf("utf8 round-trip through hexToBytes/utf8Decode failed")
	}
}

// TestParserEmit pins parser.js against the plugin message contract: single
// index, op "index", _id <chat>:<msg>, LWW doc fields, tombstone for deleted.
func TestParserEmit(t *testing.T) {
	fixtures := map[string]struct {
		raw        []byte
		wantID     string
		wantTomb   bool
		wantFields []string
	}{
		"new":     {raw: mustRead(t, "fixtures/new.json"), wantID: "101:1", wantTomb: false, wantFields: []string{"sent_at", "content"}},
		"edited":  {raw: mustRead(t, "fixtures/edited.json"), wantID: "101:1", wantTomb: false, wantFields: []string{"edited_at"}},
		"deleted": {raw: mustRead(t, "fixtures/deleted.json"), wantID: "101:1", wantTomb: true},
	}
	for name, fx := range fixtures {
		t.Run(name, func(t *testing.T) {
			contract, md := parseOutput(t, fx.raw, map[string]string{})

			var req struct {
				Index      string `json:"index"`
				Operations []struct {
					Op  string          `json:"op"`
					ID  string          `json:"id"`
					Doc json.RawMessage `json:"doc"`
				} `json:"operations"`
			}
			b, _ := json.Marshal(contract)
			if err := json.Unmarshal(b, &req); err != nil {
				t.Fatalf("emit not JSON: %v", err)
			}
			if req.Index != "budva-messages-v1" {
				t.Errorf("index = %q", req.Index)
			}
			if len(req.Operations) != 1 || req.Operations[0].Op != "index" || req.Operations[0].ID != fx.wantID {
				t.Fatalf("ops = %+v, want single index op id %s", req.Operations, fx.wantID)
			}
			var doc map[string]interface{}
			if err := json.Unmarshal(req.Operations[0].Doc, &doc); err != nil {
				t.Fatalf("doc: %v", err)
			}
			if tomb, _ := doc["tombstone"].(bool); tomb != fx.wantTomb {
				t.Errorf("tombstone = %v, want %v", doc["tombstone"], fx.wantTomb)
			}
			for _, f := range fx.wantFields {
				if _, ok := doc[f]; !ok {
					t.Errorf("doc missing field %q: %s", f, string(req.Operations[0].Doc))
				}
			}
			// The audit branch's id source must be the EXACT wire bytes.
			if got := md["rawHex"]; got != hexOf(fx.raw) {
				t.Errorf("metadata.rawHex = %v, want %q (the toHex carrier of the raw body)", got, hexOf(fx.raw))
			}
			// Invariant the plugin's strict decoder enforces (client.go index rule).
			if req.Index != strings.ToLower(req.Index) || !isLowerDNS(req.Index) {
				t.Errorf("index %q fails the plugin's ^[a-z0-9._-]+$ rule", req.Index)
			}
		})
	}
}

func isLowerDNS(s string) bool {
	if s == "" {
		return false
	}
	for _, r := range s {
		if !(r >= 'a' && r <= 'z' || r >= '0' && r <= '9' || r == '.' || r == '_' || r == '-') {
			return false
		}
	}
	return true
}

// TestParserHMAC pins the signature gate: valid accepted, tampered body /
// wrong key / missing / malformed signature dropped, and no-key no-signature
// accepted. Reference signer is Go's crypto/hmac (independent implementation).
func TestParserHMAC(t *testing.T) {
	key := "unit-test-key-0123456789"
	raw := mustRead(t, "fixtures/new.json")

	cases := []struct {
		name   string
		sig    string
		key    string
		wantOK bool
		body   []byte
	}{
		{"valid", sign(key, raw), key, true, raw},
		{"wrong_key", sign("other-key", raw), key, false, raw},
		{"missing_sig", "", key, false, raw},
		{"no_key_no_sig", "", "", true, raw},
		{"malformed_sig", "sha1=abcd", key, false, raw},
		{"tampered_body", sign(key, raw), key, false, append(append([]byte{}, raw...), ' ')},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			engine := buildEngine(t, parseScript(t), map[string]string{"budva_hmac_key": tc.key})
			meta := map[string]string{}
			if tc.sig != "" {
				meta["X-Budva-Signature"] = tc.sig
			}
			_, err := runTransform(t, engine, hexOf(tc.body), meta, "budva-to-es")
			if tc.wantOK && err != nil {
				t.Fatalf("expected accept, got failure: %v", err)
			}
			if !tc.wantOK && err == nil {
				t.Fatalf("expected drop, got accept")
			}
		})
	}
}

// TestParserRejection pins strict schema validation: bad version, unknown
// event, non-JSON body, missing message.
func TestParserRejection(t *testing.T) {
	engine := buildEngine(t, parseScript(t), nil)

	valid := string(mustRead(t, "fixtures/new.json"))
	cases := map[string]string{
		"bad_version":   strings.Replace(valid, `"schema_version": 2`, `"schema_version": 3`, 1),
		"unknown_event": strings.Replace(valid, `"event": "new"`, `"event": "archived"`, 1),
		"not_json":      `{"schema_version":2,"event":"new",`,
		"no_message":    `{"schema_version":2,"event":"new","occurred_at":"2026-01-01T00:00:00Z"}`,
	}
	for name, body := range cases {
		t.Run(name, func(t *testing.T) {
			_, err := runTransform(t, engine, hexOf([]byte(body)), map[string]string{}, "budva-to-es")
			if err == nil {
				t.Fatalf("expected rejection for %s", name)
			}
		})
	}
}

// TestEventsEmit pins the audit branch: it runs the committed events script
// on the parser's ACTUAL output (chained, as the fork delivers it) and
// asserts the single-index audit contract. The id is anchored to an
// independent reference: Go's crypto/sha256 over the same raw bytes.
func TestEventsEmit(t *testing.T) {
	fixtures := map[string][]byte{
		"new":     mustRead(t, "fixtures/new.json"),
		"edited":  mustRead(t, "fixtures/edited.json"),
		"deleted": mustRead(t, "fixtures/deleted.json"),
	}
	for name, raw := range fixtures {
		t.Run(name, func(t *testing.T) {
			contract, md := parseOutput(t, raw, map[string]string{})
			engine := buildEngine(t, eventsScript(t), nil)
			out, err := engine.Execute(nil, transform.JsTransformFuncName, contract, md, "budva-to-es", "JSON")
			if err != nil {
				t.Fatalf("events: %v", err)
			}
			res, ok := out.(map[string]interface{})
			if !ok {
				t.Fatalf("events returned %T", out)
			}
			var req struct {
				Index      string `json:"index"`
				Operations []struct {
					Op  string          `json:"op"`
					ID  string          `json:"id"`
					Doc json.RawMessage `json:"doc"`
				} `json:"operations"`
			}
			if err := json.Unmarshal([]byte(res["msg"].(string)), &req); err != nil {
				t.Fatalf("events emit not JSON: %v", err)
			}
			if req.Index != "budva-events-v1" {
				t.Errorf("index = %q", req.Index)
			}
			if len(req.Operations) != 1 {
				t.Fatalf("want exactly 1 operation, got %d", len(req.Operations))
			}
			op := req.Operations[0]
			if op.Op != "create" {
				t.Errorf("op = %q, want \"create\" (append-only, redelivery => 409 duplicate)", op.Op)
			}
			sum := sha256.Sum256(raw)
			if op.ID != hex.EncodeToString(sum[:]) {
				t.Errorf("id = %q, want Go-stdlib sha256(raw) = %q", op.ID, hex.EncodeToString(sum[:]))
			}
			var doc map[string]interface{}
			if err := json.Unmarshal(op.Doc, &doc); err != nil {
				t.Fatalf("doc: %v", err)
			}
			if ts, err := time.Parse(time.RFC3339, fmt.Sprintf("%v", doc["received_at"])); err != nil {
				t.Errorf("received_at %q not RFC3339: %v", doc["received_at"], err)
			} else if ts.Year() < 2026 {
				t.Errorf("received_at implausible: %v", ts)
			}
			for _, f := range []string{"event", "occurred_at", "chat_id", "message_id"} {
				if _, ok := doc[f]; !ok {
					t.Errorf("doc missing projected field %q: %s", f, op.Doc)
				}
			}
		})
	}
}

// TestEventsRedeliveryIsIdempotent pins the audit contract that makes the
// index a queryable delivery log: the same raw body produces the same id
// (op create), so a redelivery is an ES 409 duplicate the plugin classifies
// as success, never a second doc.
func TestEventsRedeliveryIsIdempotent(t *testing.T) {
	raw := mustRead(t, "fixtures/new.json")
	var id1, id2 string
	for i := 0; i < 2; i++ {
		contract, md := parseOutput(t, raw, map[string]string{})
		metaStrs := map[string]string{}
		for k, v := range md {
			metaStrs[k] = fmt.Sprintf("%v", v)
		}
		engine := buildEngine(t, eventsScript(t), nil)
		out, err := engine.Execute(nil, transform.JsTransformFuncName, contract, metaStrs, "budva-to-es", "JSON")
		if err != nil {
			t.Fatalf("events run %d: %v", i, err)
		}
		res := out.(map[string]interface{})
		var req struct {
			Operations []struct {
				Op string `json:"op"`
				ID string `json:"id"`
			} `json:"operations"`
		}
		if err := json.Unmarshal([]byte(res["msg"].(string)), &req); err != nil {
			t.Fatalf("run %d: %v", i, err)
		}
		if i == 0 {
			id1 = req.Operations[0].ID
		} else {
			id2 = req.Operations[0].ID
		}
	}
	if id1 != id2 {
		t.Fatalf("redelivery changed the id: %s -> %s (must be identical for op-create idempotency)", id1, id2)
	}
}

// TestEventsRejection pins the audit branch's own contract checks: it must
// fail (-> 400 via the chain) rather than emit a malformed audit doc when the
// id source or the parser contract is missing.
func TestEventsRejection(t *testing.T) {
	t.Run("missing_rawHex", func(t *testing.T) {
		contract := map[string]interface{}{
			"index": "budva-messages-v1",
			"operations": []map[string]interface{}{{
				"op": "index", "id": "1:1",
				"doc": map[string]interface{}{"chat_id": 1, "message_id": 1, "event": "new", "occurred_at": "2026-01-01T00:00:00Z"},
			}},
		}
		engine := buildEngine(t, eventsScript(t), nil)
		_, err := engine.Execute(nil, transform.JsTransformFuncName, contract, map[string]string{}, "budva-to-es", "JSON")
		if err == nil {
			t.Fatalf("expected failure without rawHex")
		}
	})
	t.Run("bad_contract", func(t *testing.T) {
		contract := map[string]interface{}{"index": "budva-messages-v1"}
		engine := buildEngine(t, eventsScript(t), nil)
		_, err := engine.Execute(nil, transform.JsTransformFuncName, contract, map[string]string{"rawHex": hexOf([]byte("{}"))}, "budva-to-es", "JSON")
		if err == nil {
			t.Fatalf("expected failure without operations[0].doc")
		}
	})
}

// TestChainEmbedsTestedScripts is the drift guard: the jsScripts chain.json
// deploys must be byte-identical to the tested sources (crypto.js+parser.js
// in the parse node, crypto.js+events.js in the audit node), and the
// load-bearing route/topology facts (processor order, wait, responseToBody,
// fork/join wiring, both write nodes on ref://) must hold. If this goes red,
// the deployed chain no longer runs what the harness tested.
func TestChainEmbedsTestedScripts(t *testing.T) {
	raw := mustRead(t, "chain.json")
	var chain struct {
		Metadata struct {
			Endpoints []struct {
				Configuration struct {
					Server string `json:"server"`
				} `json:"configuration"`
				Routers []struct {
					From struct {
						Path       string   `json:"path"`
						Processors []string `json:"processors"`
					} `json:"from"`
					To struct {
						Path       string   `json:"path"`
						Wait       bool     `json:"wait"`
						Processors []string `json:"processors"`
					} `json:"to"`
				} `json:"routers"`
			} `json:"endpoints"`
			Nodes []struct {
				Id            string `json:"id"`
				Type          string `json:"type"`
				Configuration struct {
					JsScript string `json:"jsScript"`
					Server   string `json:"server"`
					Timeout  int    `json:"timeout"`
				} `json:"configuration"`
			} `json:"nodes"`
			Connections []struct {
				FromId string `json:"fromId"`
				ToId   string `json:"toId"`
				Type   string `json:"type"`
			} `json:"connections"`
		} `json:"metadata"`
	}
	if err := json.Unmarshal(raw, &chain); err != nil {
		t.Fatalf("chain.json: %v", err)
	}

	// Exactly one router, with the load-bearing from-processor order.
	if len(chain.Metadata.Endpoints) != 1 || len(chain.Metadata.Endpoints[0].Routers) != 1 {
		t.Fatalf("expected 1 endpoint with 1 router, got %d/%d", len(chain.Metadata.Endpoints), len(chain.Metadata.Endpoints[0].Routers))
	}
	r := chain.Metadata.Endpoints[0].Routers[0]
	if got := strings.Join(r.From.Processors, ","); got != "toHex,headersToMetadata" {
		t.Errorf("from.processors = %q, want \"toHex,headersToMetadata\" (order is load-bearing)", got)
	}
	if !r.To.Wait {
		t.Errorf("to.wait = false; the response must reflect the write outcome")
	}
	if got := strings.Join(r.To.Processors, ","); got != "responseToBody" {
		t.Errorf("to.processors = %q, want \"responseToBody\"", got)
	}

	// Each node must be present with the tested script / contract.
	wantParse := parseScript(t)
	wantEvents := eventsScript(t)
	found := map[string]bool{}
	for _, n := range chain.Metadata.Nodes {
		switch n.Id {
		case "node_parse":
			ok := n.Type == "jsTransform" && n.Configuration.JsScript == wantParse
			found["node_parse"] = ok
			if !ok {
				t.Errorf("node_parse: type=%s jsScript %s the tested crypto.js+parser.js", n.Type, driftWord(n.Configuration.JsScript, wantParse))
			}
		case "node_events":
			ok := n.Type == "jsTransform" && n.Configuration.JsScript == wantEvents
			found["node_events"] = ok
			if !ok {
				t.Errorf("node_events: type=%s jsScript %s the tested crypto.js+events.js", n.Type, driftWord(n.Configuration.JsScript, wantEvents))
			}
		case "node_write", "node_write_events":
			ok := n.Type == "elasticsearchWrite" && strings.HasPrefix(n.Configuration.Server, "ref://")
			found[n.Id] = ok
			if !ok {
				t.Errorf("%s: want elasticsearchWrite on ref://, got %s %q", n.Id, n.Type, n.Configuration.Server)
			}
		case "node_fork":
			found["node_fork"] = n.Type == "fork"
		case "node_join":
			found["node_join"] = n.Type == "join" && n.Configuration.Timeout >= 45
			if n.Type == "join" && n.Configuration.Timeout < 45 {
				t.Errorf("node_join timeout = %d, want >= 45 (above the write timeout)", n.Configuration.Timeout)
			}
		}
	}
	for _, k := range []string{"node_parse", "node_events", "node_write", "node_write_events", "node_fork", "node_join"} {
		if !found[k] {
			t.Fatalf("missing or drifted node: %s", k)
		}
	}

	// Topology: parse -> fork -> both branches -> join, Success only.
	edges := map[[2]string]bool{}
	for _, c := range chain.Metadata.Connections {
		edges[[2]string{c.FromId, c.ToId}] = c.Type == "Success"
	}
	for _, e := range [][2]string{
		{"node_parse", "node_fork"},
		{"node_fork", "node_write"},
		{"node_fork", "node_events"},
		{"node_events", "node_write_events"},
		{"node_write", "node_join"},
		{"node_write_events", "node_join"},
	} {
		if !edges[e] {
			t.Errorf("missing Success edge %v -> %v", e[0], e[1])
		}
	}
	// No node may sit on a Failure edge: a failed branch is terminal and
	// fires its own OnEnd so the 400 reaches the response unmapped (spike).
	for _, c := range chain.Metadata.Connections {
		if c.Type != "Success" {
			t.Errorf("unexpected non-Success connection %v->%v type=%s", c.FromId, c.ToId, c.Type)
		}
	}
}

func driftWord(got, want string) string {
	if got == want {
		return "matches"
	}
	return "drifted from"
}
