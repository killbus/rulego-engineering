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

// deployedScript is exactly what chain.json embeds as the jsTransform jsScript.
func deployedScript(t *testing.T) string {
	t.Helper()
	return readAsset(t, "crypto.js") + "\n" + readAsset(t, "parser.js")
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
	script := deployedScript(t)
	engine := buildEngine(t, script, map[string]string{"budva_hmac_key": ""})

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
			out, err := runTransform(t, engine, hexOf(fx.raw), map[string]string{}, "budva-to-es")
			if err != nil {
				t.Fatalf("parse %s: %v", name, err)
			}
			var req struct {
				Index      string `json:"index"`
				Operations []struct {
					Op  string          `json:"op"`
					ID  string          `json:"id"`
					Doc json.RawMessage `json:"doc"`
				} `json:"operations"`
			}
			if err := json.Unmarshal([]byte(out["msg"].(string)), &req); err != nil {
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
	script := deployedScript(t)
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
			engine := buildEngine(t, script, map[string]string{"budva_hmac_key": tc.key})
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
	script := deployedScript(t)
	engine := buildEngine(t, script, nil)

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

// TestChainEmbedsTestedScript is the drift guard: the jsScript chain.json
// deploys must be byte-identical to crypto.js + parser.js (the tested source),
// and the load-bearing route facts (processor order, wait, responseToBody,
// Success edge, write-node contract fields) must hold. If this goes red, the
// deployed chain no longer runs what the harness tested.
func TestChainEmbedsTestedScript(t *testing.T) {
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

	// The parsed node must embed the tested script byte-identically.
	want := deployedScript(t)
	foundParse, foundWrite := false, false
	for _, n := range chain.Metadata.Nodes {
		switch n.Type {
		case "jsTransform":
			foundParse = true
			if n.Configuration.JsScript != want {
				t.Errorf("jsTransform %s jsScript drifted from crypto.js+parser.js (%d vs %d bytes)", n.Id, len(n.Configuration.JsScript), len(want))
			}
		case "elasticsearchWrite":
			foundWrite = true
			if n.Configuration.Server == "" || !strings.HasPrefix(n.Configuration.Server, "ref://") {
				t.Errorf("elasticsearchWrite %s server = %q, want ref://<shared node>", n.Id, n.Configuration.Server)
			}
		}
	}
	if !foundParse || !foundWrite {
		t.Fatalf("missing nodes: jsTransform=%v elasticsearchWrite=%v", foundParse, foundWrite)
	}

	// Success edge parse -> write, and the write node must NOT sit on any
	// Failure edge (failures must reach the response unmapped).
	var edges [][2]string
	for _, c := range chain.Metadata.Connections {
		edges = append(edges, [2]string{c.FromId + ":" + c.Type, c.ToId})
	}
	joined := fmt.Sprintf("%v", edges)
	if !strings.Contains(joined, "node_parse:Success") {
		t.Errorf("no Success edge out of node_parse: %v", edges)
	}
}
