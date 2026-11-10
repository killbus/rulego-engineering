package kibanaresinsubscriptionupdate_test

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"reflect"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/rulego/rulego"
	"github.com/rulego/rulego/api/types"
	endpointapi "github.com/rulego/rulego/api/types/endpoint"
	"github.com/rulego/rulego/endpoint"
	"github.com/rulego/rulego/endpoint/rest"
	"github.com/rulego/rulego/engine"
)

const subscriptionID = "12345678-1234-4234-8234-123456789abc"
const testToken = "test-token-only"

func read(t *testing.T, path string) []byte {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func marshal(t *testing.T, value any) []byte {
	t.Helper()
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func webhookBody(t *testing.T, payload map[string]any) string {
	t.Helper()
	return string(marshal(t, map[string]any{
		"schema_version": 1,
		"workflow":       "resin.subscription-url.update",
		"payload":        payload,
	}))
}

func load(t *testing.T, baseURL string) (types.RuleEngine, *rulego.RuleGo, types.Config, types.RuleChain) {
	t.Helper()
	component := read(t, "resin-subscription-update.json")
	if err := rulego.Registry.Register(engine.NewDynamicNode("resinSubscriptionUpdate", string(component))); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = rulego.Registry.Unregister("resinSubscriptionUpdate") })
	config := rulego.NewConfig()
	config.Properties = types.BuildProperties(types.Properties{
		"resin_base_url": baseURL, "resin_admin_token": testToken,
	})
	dsl := read(t, "chain.json")
	var def types.RuleChain
	if err := json.Unmarshal(dsl, &def); err != nil {
		t.Fatal(err)
	}
	pool := rulego.NewRuleGo()
	// The engine tests run without the deployment's shared :9090 resource.
	// The endpoint test below instantiates the committed route separately.
	engineDef := def
	engineDef.Metadata.Endpoints = nil
	re, err := pool.New(def.RuleChain.ID, marshal(t, engineDef), rulego.WithConfig(config))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { re.Stop(context.Background()) })
	return re, pool, config, def
}

type result struct {
	msg      types.RuleMsg
	err      error
	relation string
}

func invoke(t *testing.T, re types.RuleEngine, input string, start string, extraOptions ...types.RuleContextOption) result {
	t.Helper()
	out := make(chan result, 1)
	metadata := types.BuildMetadata(map[string]string{"correlation": "kept"})
	msg := types.NewMsg(0, "ALERT", types.JSON, metadata, input)
	opts := []types.RuleContextOption{types.WithOnEnd(func(_ types.RuleContext, msg types.RuleMsg, err error, relation string) {
		out <- result{msg, err, relation}
	})}
	if start != "" {
		opts = append(opts, types.WithStartNode(start))
	}
	opts = append(opts, extraOptions...)
	re.OnMsg(msg, opts...)
	select {
	case got := <-out:
		return got
	case <-time.After(5 * time.Second):
		t.Fatal("chain did not finish")
		return result{}
	}
}

func TestLocalContentPassesThroughGenericNode(t *testing.T) {
	// Includes quotes, Unicode, newlines, backslashes, and template-looking text.
	// None may be interpolated or escaped a second time by the HTTP node.
	content := "节点 \"A\"\nss://example#中文\\tag\n${global.not_a_variable}"
	wantBody := map[string]any{"content": content}
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		if r.Method != "PATCH" || r.URL.Path != "/resin/api/v1/subscriptions/"+subscriptionID || r.URL.RawQuery != "" {
			t.Errorf("unexpected request: %s %s", r.Method, r.URL)
		}
		if r.Header.Get("Authorization") != "Bearer "+testToken || r.Header.Get("Content-Type") != "application/json" {
			t.Error("missing authorization or JSON content type")
		}
		var body map[string]any
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Error(err)
		}
		if !reflect.DeepEqual(body, wantBody) {
			t.Errorf("body = %#v, want %#v", body, wantBody)
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"id": subscriptionID, "name": "pub-t.me/fq521", "content": content})
	}))
	defer server.Close()
	re, _, _, _ := load(t, server.URL+"/resin/")
	got := invoke(t, re, string(marshal(t, map[string]any{"id": subscriptionID, "body": wantBody})), "node_resin_update")
	if got.err != nil || got.relation != types.Success {
		t.Fatalf("result: %s %v", got.relation, got.err)
	}
	var response map[string]any
	if err := json.Unmarshal([]byte(got.msg.GetData()), &response); err != nil {
		t.Fatal(err)
	}
	if response["id"] != subscriptionID || response["content"] != content || got.msg.DataType != types.JSON {
		t.Fatalf("unexpected response: %#v", response)
	}
	if calls.Load() != 1 || got.msg.Metadata.GetValue("correlation") != "kept" || got.msg.Metadata.GetValue("statusCode") != "200" {
		t.Fatalf("calls=%d metadata=%v", calls.Load(), got.msg.Metadata.Values())
	}
	if strings.Contains(got.msg.GetData(), testToken) || strings.Contains(string(marshal(t, got.msg.Metadata.Values())), testToken) {
		t.Fatal("token leaked into output")
	}
}

func TestReusableNodeForRemoteSubscription(t *testing.T) {
	want := map[string]any{"url": "https://example.com/sub?a=1&b=2", "enabled": false}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		if !reflect.DeepEqual(body, want) || r.URL.Path != "/api/v1/subscriptions/"+subscriptionID {
			t.Errorf("unexpected PATCH: %s %#v", r.URL.Path, body)
		}
		_, _ = io.WriteString(w, `{"id":"`+subscriptionID+`","source_type":"remote"}`)
	}))
	defer server.Close()
	re, _, _, _ := load(t, server.URL)
	got := invoke(t, re, string(marshal(t, map[string]any{"id": strings.ToUpper(subscriptionID), "body": want})), "node_resin_update")
	if got.err != nil || got.relation != types.Success {
		t.Fatalf("result: %s %v", got.relation, got.err)
	}
}

func TestExtractFirstHTTPURL(t *testing.T) {
	requests := make(chan map[string]any, 1)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		if r.Method != "PATCH" || r.URL.Path != "/api/v1/subscriptions/"+subscriptionID {
			t.Errorf("unexpected request: %s %s", r.Method, r.URL)
		}
		requests <- body
		_, _ = io.WriteString(w, `{"id":"`+subscriptionID+`"}`)
	}))
	defer server.Close()
	re, _, _, _ := load(t, server.URL)
	for _, tc := range []struct{ text, url string }{
		{"订阅：https://example.com/sub?token=a%2Fb&x=1。请更新", "https://example.com/sub?token=a%2Fb&x=1"},
		{"[订阅](https://example.com/sub)\n说明", "https://example.com/sub"},
		{"(https://example.com/a(b)).", "https://example.com/a(b)"},
		{"HTTPS://example.com/sub#tag", "https://example.com/sub#tag"},
		{"http://one.example/sub https://two.example/sub", "http://one.example/sub"},
		{"ftp://files.example/sub\nhttps://real.example/sub", "https://real.example/sub"},
		{"<https://example.com/sub>", "https://example.com/sub"},
		{"https://[2001:db8::1]:8443/sub", "https://[2001:db8::1]:8443/sub"},
	} {
		t.Run(tc.text, func(t *testing.T) {
			got := invoke(t, re, webhookBody(t, map[string]any{
				"subscription_id": subscriptionID, "message_content": tc.text,
			}), "")
			if got.err != nil || got.relation != types.Success {
				t.Fatalf("result: %s %v", got.relation, got.err)
			}
			select {
			case body := <-requests:
				if !reflect.DeepEqual(body, map[string]any{"url": tc.url}) {
					t.Fatalf("PATCH body = %#v, want only url=%q", body, tc.url)
				}
			default:
				t.Fatal("no PATCH was sent")
			}
		})
	}
}

func TestNoHTTPURLIsIgnored(t *testing.T) {
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { calls.Add(1) }))
	defer server.Close()
	re, _, _, _ := load(t, server.URL)
	for _, payload := range []map[string]any{
		{}, {"message_content": nil}, {"message_content": 123},
		{"message_content": ""}, {"message_content": "公告，无链接"},
		{"message_content": "ftp://example.com/file ss://example"},
		{"message_content": "{{context.hits.0._source.message_content}}"},
		{"message_content": "https://"},
	} {
		input := webhookBody(t, payload)
		got := invoke(t, re, input, "")
		if got.err != nil || got.relation != types.Success ||
			!strings.Contains(got.msg.GetData(), `"status":"ignored"`) {
			t.Fatalf("%s -> %s %v %s", input, got.relation, got.err, got.msg.GetData())
		}
	}
	if calls.Load() != 0 {
		t.Fatalf("dropped messages sent %d requests", calls.Load())
	}
}

func TestWorkflowContract(t *testing.T) {
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { calls.Add(1) }))
	defer server.Close()
	re, _, _, _ := load(t, server.URL)
	for _, tc := range []struct{ name, input, reason string }{
		{"missing version", `{"workflow":"resin.subscription-url.update","payload":{}}`, "schema_version"},
		{"unknown version", `{"schema_version":2,"workflow":"resin.subscription-url.update","payload":{}}`, "schema_version"},
		{"old field", `{"schema_version":1,"scenario":"resin.subscription-url.update","payload":{}}`, "unsupported workflow"},
		{"unknown workflow", `{"schema_version":1,"workflow":"notification.send","payload":{}}`, "unsupported workflow"},
		{"missing payload", `{"schema_version":1,"workflow":"resin.subscription-url.update"}`, "payload must be an object"},
		{"array payload", `{"schema_version":1,"workflow":"resin.subscription-url.update","payload":[]}`, "payload must be an object"},
		{"missing target", webhookBody(t, map[string]any{"message_content": "https://example.com/sub"}), "canonical UUID"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			got := invoke(t, re, tc.input, "")
			if got.err == nil || got.relation != types.Failure || !strings.Contains(got.err.Error(), tc.reason) {
				t.Fatalf("expected %q failure, got %s %v", tc.reason, got.relation, got.err)
			}
		})
	}
	if calls.Load() != 0 {
		t.Fatalf("invalid webhook sent %d requests", calls.Load())
	}
}

func TestWorkflowUsesPayloadTarget(t *testing.T) {
	paths := make(chan string, 1)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		paths <- r.URL.Path
		_, _ = io.WriteString(w, `{}`)
	}))
	defer server.Close()
	re, _, _, _ := load(t, server.URL)
	fixture := read(t, "fixtures/alert.json")
	var envelope map[string]any
	if err := json.Unmarshal(fixture, &envelope); err != nil {
		t.Fatal(err)
	}
	for _, id := range []string{subscriptionID, "abcdef12-1234-4234-8234-123456789abc"} {
		envelope["payload"].(map[string]any)["subscription_id"] = id
		got := invoke(t, re, string(marshal(t, envelope)), "")
		if got.err != nil || got.relation != types.Success {
			t.Fatalf("result: %s %v", got.relation, got.err)
		}
		select {
		case path := <-paths:
			if path != "/api/v1/subscriptions/"+id {
				t.Fatalf("request path=%s, target=%s", path, id)
			}
		default:
			t.Fatal("no PATCH was sent")
		}
	}
}

func assertKibanaTrace(t *testing.T, msg types.RuleMsg, want map[string]string) {
	t.Helper()
	got := make(map[string]string)
	for key, value := range msg.Metadata.Values() {
		if strings.HasPrefix(key, "kibana_") {
			got[key] = value
		}
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("Kibana trace = %#v, want %#v", got, want)
	}
	if msg.Metadata.GetValue("correlation") != "kept" {
		t.Error("existing correlation metadata was lost")
	}
}

func TestKibanaTraceSurvivesWorkflowOutcomes(t *testing.T) {
	for _, tc := range []struct {
		name           string
		upstreamStatus int
		ignored        bool
	}{
		{"updated", http.StatusOK, false},
		{"ignored", http.StatusOK, true},
		{"patch failed", http.StatusBadRequest, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var envelope map[string]any
			if err := json.Unmarshal(read(t, "fixtures/alert.json"), &envelope); err != nil {
				t.Fatal(err)
			}
			wantTrace := make(map[string]string)
			for _, key := range []string{"rule_id", "rule_name", "alert_id", "timestamp"} {
				wantTrace["kibana_"+key] = envelope[key].(string)
			}
			if tc.ignored {
				envelope["payload"].(map[string]any)["message_content"] = "公告，无链接"
			}
			var calls atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				calls.Add(1)
				if r.Method != "PATCH" || r.URL.Path != "/api/v1/subscriptions/"+subscriptionID {
					t.Errorf("unexpected request: %s %s", r.Method, r.URL)
				}
				var body map[string]any
				if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
					t.Error(err)
				}
				wantBody := map[string]any{"url": "https://subscriptions.example.com/fq521?token=example-token"}
				if !reflect.DeepEqual(body, wantBody) {
					t.Errorf("PATCH body = %#v, want only %#v", body, wantBody)
				}
				for header, values := range r.Header {
					for _, value := range values {
						for _, trace := range wantTrace {
							if strings.Contains(value, trace) {
								t.Errorf("trace value leaked into header %s", header)
							}
						}
					}
				}
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(tc.upstreamStatus)
				if tc.upstreamStatus == http.StatusOK {
					_, _ = io.WriteString(w, `{"id":"`+subscriptionID+`"}`)
				} else {
					_, _ = io.WriteString(w, `{"error":"resin rejected update"}`)
				}
			}))
			defer server.Close()
			re, _, _, _ := load(t, server.URL)
			got := invoke(t, re, string(marshal(t, envelope)), "")
			if tc.upstreamStatus == http.StatusOK {
				if got.err != nil || got.relation != types.Success {
					t.Fatalf("result: %s %v", got.relation, got.err)
				}
			} else if got.err == nil || got.relation != types.Failure || !strings.Contains(got.err.Error(), "resin rejected update") {
				t.Fatalf("expected PATCH failure, got %s %v", got.relation, got.err)
			}
			if tc.ignored {
				if calls.Load() != 0 || !strings.Contains(got.msg.GetData(), `"status":"ignored"`) {
					t.Fatalf("expected ignored output and no PATCH: calls=%d data=%s", calls.Load(), got.msg.GetData())
				}
			} else if calls.Load() != 1 {
				t.Fatalf("expected one PATCH, got %d", calls.Load())
			}
			assertKibanaTrace(t, got.msg, wantTrace)
		})
	}
}

func TestKibanaTraceOptionalFieldAllowlist(t *testing.T) {
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { calls.Add(1) }))
	defer server.Close()
	re, _, _, _ := load(t, server.URL)
	for _, tc := range []struct {
		name    string
		value   any
		missing bool
	}{
		{"missing", nil, true},
		{"null", nil, false},
		{"number", 123, false},
		{"boolean", true, false},
		{"object", map[string]any{"value": "trace"}, false},
		{"array", []string{"trace"}, false},
		{"empty", "", false},
		{"blank", " \t\r\n", false},
		{"preserve original string", "  trace value\t", false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var envelope map[string]any
			if err := json.Unmarshal(read(t, "fixtures/alert.json"), &envelope); err != nil {
				t.Fatal(err)
			}
			wantTrace := make(map[string]string)
			for _, key := range []string{"rule_id", "rule_name", "alert_id", "timestamp"} {
				if tc.missing {
					delete(envelope, key)
				} else {
					envelope[key] = tc.value
				}
				if value, ok := tc.value.(string); ok && strings.TrimSpace(value) != "" {
					wantTrace["kibana_"+key] = value
				}
			}
			envelope["payload"].(map[string]any)["message_content"] = "private payload text without URL"
			envelope["admin_token"] = "private-token-must-not-copy"
			envelope["arbitrary"] = "private-arbitrary-value"
			envelope["body"] = map[string]any{"secret": "private-body-value"}
			got := invoke(t, re, string(marshal(t, envelope)), "")
			if got.err != nil || got.relation != types.Success || !strings.Contains(got.msg.GetData(), `"status":"ignored"`) {
				t.Fatalf("optional trace field blocked workflow: %s %v %s", got.relation, got.err, got.msg.GetData())
			}
			assertKibanaTrace(t, got.msg, wantTrace)
			for key := range got.msg.Metadata.Values() {
				if key != "correlation" {
					if _, ok := wantTrace[key]; !ok {
						t.Errorf("unexpected metadata field copied from envelope: %s", key)
					}
				}
			}
		})
	}
	if calls.Load() != 0 {
		t.Fatalf("ignored webhook sent %d requests", calls.Load())
	}
}

func TestWorkflowRoutingBeforeExtraction(t *testing.T) {
	for _, tc := range []struct {
		workflow string
		accepted bool
	}{
		{"resin.subscription-url.update", true},
		{"subscription-url.update", false},
		{"notification.send", false},
		{"", false},
	} {
		t.Run(tc.workflow, func(t *testing.T) {
			var calls atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				calls.Add(1)
				_, _ = io.WriteString(w, `{}`)
			}))
			defer server.Close()
			re, _, _, def := load(t, server.URL)
			snapshots := make(chan types.RuleChainRunSnapshot, 1)
			input := string(marshal(t, map[string]any{
				"schema_version": 1, "workflow": tc.workflow,
				"payload": map[string]any{"subscription_id": subscriptionID, "message_content": "https://example.com/sub"},
			}))
			// Debug callbacks are asynchronous; use the completed execution snapshot.
			got := invoke(t, re, input, "", types.WithOnRuleChainCompleted(func(_ types.RuleContext, snapshot types.RuleChainRunSnapshot) {
				snapshots <- snapshot
			}))
			if tc.accepted && (got.err != nil || got.relation != types.Success || calls.Load() != 1) {
				t.Fatalf("known workflow: %s %v calls=%d", got.relation, got.err, calls.Load())
			}
			if !tc.accepted && (got.err == nil || got.relation != types.Failure || calls.Load() != 0) {
				t.Fatalf("unknown workflow: %s %v calls=%d", got.relation, got.err, calls.Load())
			}
			visited := map[string]bool{}
			select {
			case snapshot := <-snapshots:
				for _, log := range snapshot.Logs {
					visited[log.Id] = log.StartTs > 0
				}
			case <-time.After(5 * time.Second):
				t.Fatal("chain did not publish its execution snapshot")
			}
			if !visited["node_validate"] || !visited["node_route"] ||
				visited["node_5"] != tc.accepted || visited["node_unsupported"] == tc.accepted {
				t.Fatalf("incorrect branch execution: %v", visited)
			}
			if def.RuleChain.Name != "kibana-webhook-ingress" {
				t.Fatalf("unexpected ingress name: %s", def.RuleChain.Name)
			}
		})
	}
}

func TestInvalidInputDoesNotSend(t *testing.T) {
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { calls.Add(1) }))
	defer server.Close()
	re, _, _, _ := load(t, server.URL)
	for _, tc := range []struct{ name, input, start, reason string }{
		{"name is not id", `{"name":"pub-t.me/fq521","body":{"content":"x"}}`, "node_resin_update", "canonical UUID"},
		{"path injection", `{"id":"../other","body":{"content":"x"}}`, "node_resin_update", "canonical UUID"},
		{"empty patch", `{"id":"` + subscriptionID + `","body":{}}`, "node_resin_update", "non-empty JSON object"},
		{"array patch", `{"id":"` + subscriptionID + `","body":[]}`, "node_resin_update", "non-empty JSON object"},
		{"string patch", `{"id":"` + subscriptionID + `","body":"{}"}`, "node_resin_update", "non-empty JSON object"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			got := invoke(t, re, tc.input, tc.start)
			if got.err == nil || got.relation != types.Failure || !strings.Contains(got.err.Error(), tc.reason) {
				t.Fatalf("expected %q failure, got %s %v", tc.reason, got.relation, got.err)
			}
		})
	}
	if calls.Load() != 0 {
		t.Fatalf("invalid inputs sent %d requests", calls.Load())
	}
}

func TestHTTPResponseWaitsForPatchAndPropagatesFailure(t *testing.T) {
	var envelope map[string]any
	if err := json.Unmarshal(read(t, "fixtures/alert.json"), &envelope); err != nil {
		t.Fatal(err)
	}
	input := string(marshal(t, envelope))
	assertNoTraceInResponse := func(body string) {
		t.Helper()
		for _, key := range []string{"rule_id", "rule_name", "alert_id", "timestamp"} {
			if strings.Contains(body, envelope[key].(string)) {
				t.Errorf("trace field %s leaked into webhook response: %s", key, body)
			}
		}
	}
	var status atomic.Int32
	var calls atomic.Int32
	status.Store(200)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		calls.Add(1)
		code := int(status.Load())
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(code)
		if code == 200 {
			_, _ = io.WriteString(w, `{"id":"`+subscriptionID+`","name":"pub-t.me/fq521"}`)
		} else {
			_, _ = io.WriteString(w, `{"error":{"code":"TEST_ERROR","message":"resin rejected update"}}`)
		}
	}))
	defer server.Close()
	_, pool, config, def := load(t, server.URL)
	epDef := *def.Metadata.Endpoints[0]
	// Keep the committed route/processors; replace only the deployment's shared listener.
	epDef.Configuration["server"] = "127.0.0.1:0"
	ep, err := endpoint.NewFromDef(epDef,
		endpointapi.DynamicEndpointOptions.WithConfig(config),
		endpointapi.DynamicEndpointOptions.WithRouterOpts(endpointapi.RouterOptions.WithRuleGo(pool)))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(ep.Destroy)
	handler := ep.Target().(*rest.Rest).Router()
	for _, upstreamStatus := range []int{200, 400, 401, 404, 500} {
		status.Store(int32(upstreamStatus))
		req := httptest.NewRequest("POST", "/webhooks/kibana", strings.NewReader(input))
		req.Header.Set("Content-Type", "application/json")
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, req)
		if upstreamStatus == 200 {
			if recorder.Code != 200 || !strings.Contains(recorder.Body.String(), subscriptionID) {
				t.Fatalf("success response did not wait for PATCH: %d %s", recorder.Code, recorder.Body)
			}
		} else if recorder.Code != 400 || !strings.Contains(recorder.Body.String(), "resin rejected update") {
			t.Fatalf("upstream %d became %d %s", upstreamStatus, recorder.Code, recorder.Body)
		}
		assertNoTraceInResponse(recorder.Body.String())
	}
	before := calls.Load()
	envelope["payload"].(map[string]any)["message_content"] = "无链接"
	for _, tc := range []struct {
		body   string
		status int
		reason string
	}{
		{`{"schema_version":1,"workflow":"notification.send","payload":{"message_content":"https://example.com/sub"}}`, 400, "unsupported workflow"},
		{string(marshal(t, envelope)), 200, "no_http_url"},
	} {
		req := httptest.NewRequest("POST", "/webhooks/kibana", strings.NewReader(tc.body))
		req.Header.Set("Content-Type", "application/json")
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, req)
		if recorder.Code != tc.status || !strings.Contains(recorder.Body.String(), tc.reason) {
			t.Fatalf("expected %d %s, got %d %s", tc.status, tc.reason, recorder.Code, recorder.Body)
		}
		assertNoTraceInResponse(recorder.Body.String())
	}
	if calls.Load() != before {
		t.Fatal("rejected or ignored webhook called Resin")
	}
}

func TestEmbeddedScripts(t *testing.T) {
	for _, tc := range []struct{ dsl, node, script string }{
		{"chain.json", "node_validate", "validate-webhook.js"},
		{"chain.json", "node_5", "alert-to-update.js"},
		{"resin-subscription-update.json", "prepare", "prepare-update.js"},
	} {
		var def types.RuleChain
		if err := json.Unmarshal(read(t, tc.dsl), &def); err != nil {
			t.Fatal(err)
		}
		node, ok := def.GetNode(tc.node)
		if !ok || node.Configuration["jsScript"] != string(read(t, tc.script)) {
			t.Fatalf("%s differs from %s: run node build.mjs", tc.dsl, tc.script)
		}
	}
}
