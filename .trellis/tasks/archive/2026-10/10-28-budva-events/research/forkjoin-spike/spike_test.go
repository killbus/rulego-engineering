// Spike: verify the rulego v1.0.0 fork/join + wait:true + responseToBody
// interaction that the Phase-2 budva-events-v1 audit topology depends on.
// These are OBSERVATIONS (printed + hard-contract asserted), not assumptions.
//
// Topologies (all over real HTTP on localhost, wait:true, responseToBody):
//
//	T1 fork -> [wA, wB] -> join : both ok -> 200, one merged body, waits both
//	T4 fork -> [wA(fail), wB(ok)] -> join : is the failed write visible (400)?
package main

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	rulego "github.com/rulego/rulego"
	"github.com/rulego/rulego/api/types"
)

type endCounter struct {
	Success atomic.Int64
	Failure atomic.Int64
}

// chainJSON builds a root chain: http endpoint (wait, responseToBody) ->
// fork1 -> [wA, wB] -> (join1 if join) . branchA/branchB are the proxy config
// JSON for each write node.
func chainJSON(id string, port int, branchA, branchB string, join bool, joinTimeout int) string {
	nodes := []string{
		`{"id":"fork1","type":"fork","name":"fork"}`,
		`{"id":"wA","type":"esWriteProxy","name":"wA","configuration":` + branchA + `}`,
		`{"id":"wB","type":"esWriteProxy","name":"wB","configuration":` + branchB + `}`,
	}
	conns := []string{
		`{"fromId":"fork1","toId":"wA","type":"Success"}`,
		`{"fromId":"fork1","toId":"wB","type":"Success"}`,
	}
	if join {
		nodes = append(nodes,
			`{"id":"join1","type":"join","name":"join","configuration":{"timeout":`+itoa(joinTimeout)+`}}`)
		conns = append(conns,
			`{"fromId":"wA","toId":"join1","type":"Success"}`,
			`{"fromId":"wB","toId":"join1","type":"Success"}`)
	}
	var sb strings.Builder
	sb.WriteString(`{"ruleChain":{"id":"`)
	sb.WriteString(id)
	sb.WriteString(`","name":"`)
	sb.WriteString(id)
	sb.WriteString(`","root":true,"debugMode":false},"metadata":{"endpoints":[{"id":"ep","type":"endpoint/http","name":"ep","configuration":{"server":":`)
	sb.WriteString(itoa(port))
	sb.WriteString(`"},"routers":[{"id":"r1","params":["POST"],"from":{"path":"/p","configuration":null},"to":{"path":"`)
	sb.WriteString(id)
	sb.WriteString(`:fork1","wait":true,"processors":["responseToBody"]}}]}],"nodes":[`)
	sb.WriteString(strings.Join(nodes, ","))
	sb.WriteString(`],"connections":[`)
	sb.WriteString(strings.Join(conns, ","))
	sb.WriteString(`]}}`)
	return sb.String()
}

func itoa(v int) string { return fmt.Sprintf("%d", v) }

func startEngine(t *testing.T, id, src string, ec *endCounter) {
	t.Helper()
	// WithOnEndGlobal counts every terminal-branch OnEnd the endpoint sees.
	config := rulego.NewConfig(
		types.WithDefaultPool(),
		types.WithEndpointEnabled(true),
		types.WithOnEndGlobal(func(ctx types.RuleContext, msg types.RuleMsg, err error, relationType string) {
			if err != nil {
				ec.Failure.Add(1)
				fmt.Printf("    [onend] relation=%s ERR=%v msg=%.160s\n", relationType, err, msg.GetData())
			} else {
				ec.Success.Add(1)
				fmt.Printf("    [onend] relation=%s msg=%.160s\n", relationType, msg.GetData())
			}
		}),
	)
	eng, err := rulego.New(id, []byte(src), types.WithConfig(config))
	if err != nil {
		t.Fatalf("engine start %s: %v", id, err)
	}
	time.Sleep(700 * time.Millisecond)
	t.Cleanup(func() { eng.Stop(context.Background()) })
}

func post(port int, body string, timeout time.Duration) (int, string, time.Duration, error) {
	client := &http.Client{Timeout: timeout}
	start := time.Now()
	resp, err := client.Post(fmt.Sprintf("http://127.0.0.1:%d/p", port), "application/json", strings.NewReader(body))
	lat := time.Since(start)
	if err != nil {
		return 0, "", lat, err
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(resp.Body)
	return resp.StatusCode, string(b), lat, nil
}

func TestT1_ForkJoinBothOK(t *testing.T) {
	RegisterProxyNode()
	ec := &endCounter{}
	port := 9101
	src := chainJSON("t1", port, `{"fail":false,"delayMs":120}`, `{"fail":false,"delayMs":40}`, true, 10)
	startEngine(t, "t1", src, ec)

	st, body, lat, err := post(port, `{"i":1}`, 20*time.Second)
	if err != nil {
		t.Fatalf("T1 request: %v", err)
	}
	fmt.Printf("T1 status=%d lat=%v onEnd(succ/fail)=%d/%d\nT1 body=%s\n",
		st, lat, ec.Success.Load(), ec.Failure.Load(), body)

	if st != 200 {
		t.Fatalf("T1: want 200, got %d (body=%s)", st, body)
	}
	if ec.Success.Load() != 1 {
		t.Fatalf("T1: want exactly ONE terminal OnEnd (deterministic join), got %d", ec.Success.Load())
	}
	// default join (mergeToMap:false) -> array of both branch results.
	if !strings.Contains(body, `nodeId":"wA"`) || !strings.Contains(body, `nodeId":"wB"`) {
		t.Fatalf("T1: default join body must contain BOTH branches, got: %s", body)
	}
	if lat < 120*time.Millisecond {
		t.Errorf("T1: lat %v < 120ms: response did not wait for the slower branch", lat)
	}
}

func TestT4_ForkJoinOneFails(t *testing.T) {
	RegisterProxyNode()
	ec := &endCounter{}
	port := 9104
	// wA fails fast, wB ok. join timeout 2s: if a failed branch never reaches
	// the join, the join must wait 2s then TellFailure -> 400 (slow 400). If
	// the engine surfaces it fast, that is a better contract (printed as a
	// finding). Either way the status MUST be 400: a 200 here means the failed
	// write is masked, breaking the "response reflects both writes" contract.
	src := chainJSON("t4", port, `{"fail":true,"delayMs":0}`, `{"fail":false,"delayMs":50}`, true, 2)
	startEngine(t, "t4", src, ec)

	st, body, lat, err := post(port, `{"i":1}`, 20*time.Second)
	if err != nil {
		t.Fatalf("T4 request: join did not release (lat=%v): %v", lat, err)
	}
	fmt.Printf("T4 status=%d lat=%v onEnd(succ/fail)=%d/%d\nT4 body=%s\n",
		st, lat, ec.Success.Load(), ec.Failure.Load(), body)

	if st != 400 {
		t.Fatalf("T4: failed write MASKED (status %d, want 400): body=%s", st, body)
	}
	if lat >= 1800*time.Millisecond {
		fmt.Printf("T4 OBSERVATION: slow 400 (lat=%v) - failed branch did not reach join; join waited its timeout\n", lat)
	} else {
		fmt.Printf("T4 OBSERVATION: fast 400 (lat=%v) - failure surfaced without waiting the join timeout\n", lat)
	}
}
