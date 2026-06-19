// Command parity replays the parity MATRIX + PAGI through the generated Go
// bindings and the hand-written runtime, emitting one canonical-request JSON
// line per check. go_parity.py diffs each line against the Python executor.
package main

import (
	"bufio"
	_ "embed"
	"encoding/json"
	"os"

	"tcspike"
)

//go:embed matrix.json
var matrixJSON []byte

type matrixRow struct {
	Connector string         `json:"connector"`
	Cred      string         `json:"cred"`
	Action    string         `json:"action"`
	Args      map[string]any `json:"args"`
}

type pagiRow struct {
	Connector string            `json:"connector"`
	Cred      string            `json:"cred"`
	Action    string            `json:"action"`
	FirstArgs map[string]any    `json:"first_args"`
	Body      map[string]any    `json:"body"`
	Headers   map[string]string `json:"headers"`
}

type matrixFile struct {
	Matrix []matrixRow `json:"matrix"`
	Pagi   []pagiRow   `json:"pagi"`
}

// row is the cross-language canonical-request contract (matches parity.ts).
type row struct {
	Kind      string      `json:"kind"`
	Connector string      `json:"connector"`
	Action    string      `json:"action"`
	Method    string      `json:"method"`
	Host      string      `json:"host"`
	Path      string      `json:"path"`
	Query     [][2]string `json:"query"`
	Body      *string     `json:"body"`
	Auth      *string     `json:"auth"`
	None      bool        `json:"none,omitempty"`
}

func main() {
	var mf matrixFile
	if err := json.Unmarshal(matrixJSON, &mf); err != nil {
		panic(err)
	}
	w := bufio.NewWriter(os.Stdout)
	defer w.Flush()
	enc := json.NewEncoder(w)

	for _, r := range mf.Matrix {
		br := tcspike.BuildRequest(tcspike.ALL[r.Connector], r.Action, r.Args, r.Cred)
		emit(enc, "first", r.Connector, r.Action, &br)
	}
	for _, r := range mf.Pagi {
		br := tcspike.NextRequest(tcspike.ALL[r.Connector], r.Action, r.FirstArgs, r.Cred, r.Body, r.Headers)
		emit(enc, "next", r.Connector, r.Action, br)
	}
}

func emit(enc *json.Encoder, kind, conn, action string, br *tcspike.BuiltRequest) {
	if br == nil {
		_ = enc.Encode(row{Kind: kind, Connector: conn, Action: action, None: true})
		return
	}
	q := br.Query
	if q == nil {
		q = [][2]string{}
	}
	_ = enc.Encode(row{
		Kind: kind, Connector: conn, Action: action,
		Method: br.Method, Host: br.Host, Path: br.Path,
		Query: q, Body: br.Body, Auth: br.Auth,
	})
}
