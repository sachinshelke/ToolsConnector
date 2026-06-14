// Package toolsconnector is the thin, hand-written Go runtime for the spec-driven SDK.
//
// It is the Go sibling of executor.py / runtime.ts: given a ConnectorB + an
// action name + a map of arguments, BuildRequest produces the EXACT request the
// hand-written connector would send, and NextRequest computes the follow-up
// request for pagination. This ~one-file interpreter is the ONLY per-language
// code a Smithy-style generator hand-writes (once per language). Everything else
// — the typed action methods + the bindings — is generated from the declarative
// spec. The spike proves this finite interpreter reproduces the imperative
// connectors byte-for-byte, now across Python, TypeScript AND Go.
package toolsconnector

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

// ---------------------------------------------------------------------------
// Binding IR (mirrors binding_ir.py; JSON tags match the Pydantic field names)
// ---------------------------------------------------------------------------

type Param struct {
	Name           string         `json:"name"`
	Wire           string         `json:"wire"`
	Location       string         `json:"location"` // path|query|header|body
	Style          string         `json:"style"`    // simple|indexed|indexed_object|bracket|form_explode|map
	Required       bool           `json:"required"`
	Default        any            `json:"default"`
	Ty             *string        `json:"ty"`
	Subkeys        []string       `json:"subkeys"`
	SubkeyDefaults map[string]any `json:"subkey_defaults"`
	BodyKey        *string        `json:"body_key"`
	ItemWrap       *string        `json:"item_wrap"`
	Max            *int           `json:"max"`
	MaxItems       *int           `json:"max_items"`
}

type Pagination struct {
	Kind         string   `json:"kind"` // none|offset_token|link_header|follow_url|last_id
	ItemsField   *string  `json:"items_field"`
	TokenField   *string  `json:"token_field"`
	TokenParamPy *string  `json:"token_param_py"`
	LinkRel      string   `json:"link_rel"`
	IDField      string   `json:"id_field"`
	HasMoreField string   `json:"has_more_field"`
	Carry        []string `json:"carry"`
}

type Action struct {
	Name         string     `json:"name"`
	Method       string     `json:"method"`
	Endpoint     string     `json:"endpoint"`
	Path         string     `json:"path"`
	Params       []Param    `json:"params"`
	BodyWrap     *string    `json:"body_wrap"`
	BodyEncoding *string    `json:"body_encoding"`
	Unwrap       *string    `json:"unwrap"`
	Pagination   Pagination `json:"pagination"`
}

type Endpoint struct {
	ID           string            `json:"id"`
	BaseURL      string            `json:"base_url"`
	Encoding     string            `json:"encoding"` // json|form
	AuthKind     string            `json:"auth_kind"`
	AuthHeader   string            `json:"auth_header"`
	AuthCredCtx  *string           `json:"auth_cred_ctx"`
	ExtraHeaders map[string]string `json:"extra_headers"`
}

type CtxVar struct {
	Name   string `json:"name"`
	Source string `json:"source"`
}

type ConnectorB struct {
	Name            string              `json:"name"`
	Endpoints       map[string]Endpoint `json:"endpoints"`
	DefaultEndpoint string              `json:"default_endpoint"`
	CtxVars         []CtxVar            `json:"ctx_vars"`
	Actions         map[string]Action   `json:"actions"`
	EscapeHatches   []string            `json:"escape_hatches"`
}

// BuiltRequest is the canonical request the runtime produces. Query is kept as
// ordered pairs (decoded) so the cross-language parity gate can compare them
// directly against httpx's multi_items().
type BuiltRequest struct {
	Method      string
	URL         string // base + path, WITHOUT the query string
	Scheme      string
	Host        string
	Path        string
	Query       [][2]string
	Body        *string
	ContentType *string
	Headers     map[string]string
	Auth        *string
}

// MustParseBinding unmarshals a binding JSON blob (emitted by gen_go.py) into a
// ConnectorB. Panics on malformed input — bindings are generated, not user data.
func MustParseBinding(js string) *ConnectorB {
	var c ConnectorB
	if err := json.Unmarshal([]byte(js), &c); err != nil {
		panic(fmt.Sprintf("binding parse: %v", err))
	}
	return &c
}

// ---------------------------------------------------------------------------
// Context derivation (credential -> template vars)
// ---------------------------------------------------------------------------

func DeriveCtx(conn *ConnectorB, credential string) map[string]string {
	ctx := map[string]string{}
	for _, cv := range conn.CtxVars {
		if cv.Source == "whole" {
			ctx[cv.Name] = credential
		} else if strings.HasPrefix(cv.Source, "split:") {
			rest := strings.SplitN(cv.Source, ":", 3) // ["split", idx, sep]
			idx, _ := strconv.Atoi(rest[1])
			sep := rest[2]
			parts := strings.Split(credential, sep)
			if idx < len(parts) {
				ctx[cv.Name] = parts[idx]
			} else {
				ctx[cv.Name] = ""
			}
		}
	}
	return ctx
}

func authCred(ep Endpoint, credential string, ctx map[string]string) string {
	if ep.AuthCredCtx != nil {
		return ctx[*ep.AuthCredCtx]
	}
	return credential
}

// applyAuth sets the auth header and returns its value (or nil if none applied).
func applyAuth(headers map[string]string, ep Endpoint, cred string) *string {
	var val string
	switch ep.AuthKind {
	case "bearer":
		val = "Bearer " + cred
	case "header_key":
		val = cred
	case "basic_split":
		val = "Basic " + base64.StdEncoding.EncodeToString([]byte(cred))
	case "basic_user": // API key as username, empty password: base64("<key>:")
		val = "Basic " + base64.StdEncoding.EncodeToString([]byte(cred+":"))
	default:
		return nil
	}
	headers[ep.AuthHeader] = val
	return &val
}

// ---------------------------------------------------------------------------
// Serialization
// ---------------------------------------------------------------------------

func present(v any) bool { return v != nil }

// str mirrors Python's str() for the value types that reach the wire. JSON
// numbers arrive as float64; integral ones format without a decimal point so
// str(100) == "100" (not "100.000000"), matching the Python reference.
func str(v any) string {
	switch x := v.(type) {
	case nil:
		return "None"
	case bool:
		if x {
			return "True"
		}
		return "False"
	case string:
		return x
	case float64:
		if x == math.Trunc(x) && !math.IsInf(x, 0) {
			return strconv.FormatInt(int64(x), 10)
		}
		return strconv.FormatFloat(x, 'f', -1, 64)
	case int:
		return strconv.Itoa(x)
	case int64:
		return strconv.FormatInt(x, 10)
	default:
		return fmt.Sprintf("%v", x)
	}
}

// The runtime must accept values from two sources: JSON-decoded args (the parity
// harness: []any / map[string]any) AND a typed client's Go-native args
// ([]string / map[string]string / []map[string]string). These coercions
// normalize both into the shapes the serializer walks.

func toSeq(v any) []any {
	switch x := v.(type) {
	case []any:
		return x
	case []string:
		out := make([]any, len(x))
		for i, e := range x {
			out[i] = e
		}
		return out
	case []map[string]string:
		out := make([]any, len(x))
		for i, e := range x {
			out[i] = e
		}
		return out
	case []map[string]any:
		out := make([]any, len(x))
		for i, e := range x {
			out[i] = e
		}
		return out
	}
	return nil
}

func toStrMap(v any) map[string]string {
	switch x := v.(type) {
	case map[string]string:
		return x
	case map[string]any:
		out := make(map[string]string, len(x))
		for k, e := range x {
			out[k] = str(e)
		}
		return out
	}
	return nil
}

func toAnyMap(v any) map[string]any {
	switch x := v.(type) {
	case map[string]any:
		return x
	case map[string]string:
		out := make(map[string]any, len(x))
		for k, e := range x {
			out[k] = e
		}
		return out
	}
	return nil
}

func clamp(v any, mx *int) any {
	if mx == nil {
		return v
	}
	if f, ok := v.(float64); ok {
		return math.Min(f, float64(*mx))
	}
	if i, ok := v.(int); ok {
		if i > *mx {
			return *mx
		}
		return i
	}
	return v
}

func asSeq(v any, maxItems *int) []any {
	seq := toSeq(v)
	if maxItems != nil && len(seq) > *maxItems {
		return seq[:*maxItems]
	}
	return seq
}

// styledPairs serializes ONE present param value into wire (key,value) pairs by
// style — shared by query strings AND form bodies (Stripe puts list/object
// params in the body too).
func styledPairs(p Param, v any) [][2]string {
	switch p.Style {
	case "indexed":
		seq := asSeq(v, p.MaxItems)
		out := make([][2]string, len(seq))
		for i, item := range seq {
			out[i] = [2]string{fmt.Sprintf("%s[%d]", p.Wire, i), str(item)}
		}
		return out
	case "indexed_object":
		var out [][2]string
		for i, item := range asSeq(v, nil) {
			m := toAnyMap(item)
			for _, sk := range p.Subkeys {
				val, ok := m[sk]
				if !ok {
					val = p.SubkeyDefaults[sk]
				}
				out = append(out, [2]string{fmt.Sprintf("%s[%d][%s]", p.Wire, i, sk), str(val)})
			}
		}
		return out
	case "bracket":
		seq := asSeq(v, p.MaxItems)
		out := make([][2]string, len(seq))
		for i, item := range seq {
			out[i] = [2]string{p.Wire + "[]", str(item)}
		}
		return out
	case "form_explode":
		seq := asSeq(v, nil)
		out := make([][2]string, len(seq))
		for i, item := range seq {
			out[i] = [2]string{p.Wire, str(item)}
		}
		return out
	case "map":
		m := toStrMap(v)
		keys := make([]string, 0, len(m))
		for k := range m {
			keys = append(keys, k)
		}
		sort.Strings(keys) // deterministic; the parity gate sorts pairs anyway
		out := make([][2]string, len(keys))
		for i, k := range keys {
			out[i] = [2]string{fmt.Sprintf("%s[%s]", p.Wire, k), m[k]}
		}
		return out
	default: // simple
		return [][2]string{{p.Wire, str(clamp(v, p.Max))}}
	}
}

func argOrDefault(args map[string]any, p Param) any {
	if v, ok := args[p.Name]; ok {
		return v
	}
	return p.Default
}

func queryPairs(action Action, args map[string]any) [][2]string {
	var out [][2]string
	for _, p := range action.Params {
		if p.Location != "query" {
			continue
		}
		if v := argOrDefault(args, p); present(v) {
			out = append(out, styledPairs(p, v)...)
		}
	}
	return out
}

func buildBody(action Action, encoding string, args map[string]any) (body *string, contentType *string) {
	var bodyParams []Param
	for _, p := range action.Params {
		if p.Location == "body" {
			bodyParams = append(bodyParams, p)
		}
	}
	if len(bodyParams) == 0 {
		return nil, nil
	}

	if encoding == "form" {
		var pairs [][2]string
		for _, p := range bodyParams {
			if v := argOrDefault(args, p); present(v) {
				pairs = append(pairs, styledPairs(p, v)...)
			}
		}
		parts := make([]string, len(pairs))
		for i, kv := range pairs {
			parts[i] = url.QueryEscape(kv[0]) + "=" + url.QueryEscape(kv[1])
		}
		s := strings.Join(parts, "&")
		ct := "application/x-www-form-urlencoded"
		return &s, &ct
	}

	// JSON
	obj := map[string]any{}
	for _, p := range bodyParams {
		v := argOrDefault(args, p)
		if !present(v) {
			continue
		}
		if p.ItemWrap != nil {
			seq := asSeq(v, p.MaxItems)
			wrapped := make([]any, len(seq))
			for i, elem := range seq {
				wrapped[i] = map[string]any{*p.ItemWrap: elem}
			}
			v = wrapped
		}
		key := p.Wire
		if p.BodyKey != nil {
			key = *p.BodyKey
		}
		obj[key] = v
	}
	var final any = obj
	if action.BodyWrap != nil {
		final = map[string]any{*action.BodyWrap: obj}
	}
	b, _ := json.Marshal(final)
	s := string(b)
	ct := "application/json"
	return &s, &ct
}

var ctxVarRe = regexp.MustCompile(`\{(\w+)\}`)

// fmtTemplate substitutes {key} placeholders from the merged maps (later maps win).
func fmtTemplate(s string, maps ...map[string]any) string {
	return ctxVarRe.ReplaceAllStringFunc(s, func(m string) string {
		key := m[1 : len(m)-1]
		for i := len(maps) - 1; i >= 0; i-- {
			if v, ok := maps[i][key]; ok {
				return str(v)
			}
		}
		return m
	})
}

func ctxAsAny(ctx map[string]string) map[string]any {
	m := make(map[string]any, len(ctx))
	for k, v := range ctx {
		m[k] = v
	}
	return m
}

// ---------------------------------------------------------------------------
// Request building
// ---------------------------------------------------------------------------

func BuildRequest(conn *ConnectorB, actionName string, args map[string]any, credential string) BuiltRequest {
	action := conn.Actions[actionName]
	ep := conn.Endpoints[action.Endpoint]
	ctx := DeriveCtx(conn, credential)
	ctxAny := ctxAsAny(ctx)

	// 1) path: substitute {ctx} + {path params}
	subst := map[string]any{}
	for k, v := range ctxAny {
		subst[k] = v
	}
	for _, p := range action.Params {
		if p.Location == "path" {
			subst[p.Wire] = argOrDefault(args, p)
		}
	}
	base := fmtTemplate(ep.BaseURL, ctxAny)
	path := fmtTemplate(action.Path, subst)
	urlStr := strings.TrimRight(base, "/") + "/" + strings.TrimLeft(path, "/")

	// 2) query
	query := queryPairs(action, args)

	// 3) body
	encoding := ep.Encoding
	if action.BodyEncoding != nil {
		encoding = *action.BodyEncoding
	}
	body, contentType := buildBody(action, encoding, args)

	// 4) headers
	headers := map[string]string{}
	for k, v := range ep.ExtraHeaders {
		headers[k] = v
	}
	for _, p := range action.Params {
		if p.Location == "header" {
			if v := argOrDefault(args, p); present(v) {
				headers[p.Wire] = str(v)
			}
		}
	}
	auth := applyAuth(headers, ep, authCred(ep, credential, ctx))
	if contentType != nil {
		headers["content-type"] = *contentType
	}

	u, _ := url.Parse(urlStr)
	return BuiltRequest{
		Method: action.Method, URL: urlStr, Scheme: u.Scheme, Host: u.Host, Path: u.Path,
		Query: query, Body: body, ContentType: contentType, Headers: headers, Auth: auth,
	}
}

// ---------------------------------------------------------------------------
// Pagination — compute the next-page request
// ---------------------------------------------------------------------------

var linkRe = regexp.MustCompile(`<([^>]+)>;\s*rel="?(\w+)"?`)
var pageInfoRe = regexp.MustCompile(`[?&]page_info=([^&>]+)`)

func parseLinkNext(linkHeader, rel string) *string {
	if linkHeader == "" {
		return nil
	}
	for _, m := range linkRe.FindAllStringSubmatch(linkHeader, -1) {
		if m[2] == rel {
			if pm := pageInfoRe.FindStringSubmatch(m[1]); pm != nil {
				return &pm[1]
			}
		}
	}
	return nil
}

func carryArgs(prevArgs map[string]any, carry []string) map[string]any {
	n := map[string]any{}
	if carry == nil {
		for k, v := range prevArgs {
			n[k] = v
		}
		return n
	}
	for _, k := range carry {
		if v, ok := prevArgs[k]; ok {
			n[k] = v
		}
	}
	return n
}

// NextRequest returns the follow-up request for pagination, or nil when the last
// page has been reached. body/headers are the previous response's parsed body
// and headers.
func NextRequest(conn *ConnectorB, actionName string, prevArgs map[string]any, credential string,
	body map[string]any, headers map[string]string) *BuiltRequest {
	action := conn.Actions[actionName]
	ep := conn.Endpoints[action.Endpoint]
	ctx := DeriveCtx(conn, credential)
	pg := action.Pagination
	if body == nil {
		body = map[string]any{}
	}
	if headers == nil {
		headers = map[string]string{}
	}

	switch pg.Kind {
	case "follow_url":
		if pg.TokenField == nil {
			return nil
		}
		uriV, ok := body[*pg.TokenField]
		uri, _ := uriV.(string)
		if !ok || uri == "" {
			return nil
		}
		baseU, _ := url.Parse(fmtTemplate(ep.BaseURL, ctxAsAny(ctx)))
		refU, _ := url.Parse(uri)
		joined := baseU.ResolveReference(refU)
		h := map[string]string{}
		for k, v := range ep.ExtraHeaders {
			h[k] = v
		}
		auth := applyAuth(h, ep, authCred(ep, credential, ctx))
		req := BuiltRequest{
			Method: "GET", URL: joined.String(), Scheme: joined.Scheme, Host: joined.Host,
			Path: joined.Path, Query: linkQuery(joined), Headers: h, Auth: auth,
		}
		return &req

	case "offset_token":
		if pg.TokenField == nil {
			return nil
		}
		cursor, ok := body[*pg.TokenField]
		if !ok || cursor == nil {
			return nil
		}
		n := carryArgs(prevArgs, pg.Carry)
		n[*pg.TokenParamPy] = cursor
		req := BuildRequest(conn, actionName, n, credential)
		return &req

	case "last_id":
		var items []any
		if pg.ItemsField != nil {
			items, _ = body[*pg.ItemsField].([]any)
		}
		hasMore, _ := body[pg.HasMoreField].(bool)
		if !hasMore || len(items) == 0 {
			return nil
		}
		last, _ := items[len(items)-1].(map[string]any)
		cursor, ok := last[pg.IDField]
		if !ok || cursor == nil {
			return nil
		}
		n := carryArgs(prevArgs, pg.Carry)
		n[*pg.TokenParamPy] = cursor
		req := BuildRequest(conn, actionName, n, credential)
		return &req

	case "link_header":
		cursor := parseLinkNext(headers["link"], pg.LinkRel)
		if cursor == nil {
			return nil
		}
		n := carryArgs(prevArgs, pg.Carry)
		n[*pg.TokenParamPy] = *cursor
		req := BuildRequest(conn, actionName, n, credential)
		return &req
	}
	return nil
}

// linkQuery decodes a resolved follow_url's query into ordered pairs so the
// parity gate compares the same shape build_request produces for other kinds.
func linkQuery(u *url.URL) [][2]string {
	if u.RawQuery == "" {
		return nil
	}
	var out [][2]string
	for _, part := range strings.Split(u.RawQuery, "&") {
		kv := strings.SplitN(part, "=", 2)
		k, _ := url.QueryUnescape(kv[0])
		v := ""
		if len(kv) > 1 {
			v, _ = url.QueryUnescape(kv[1])
		}
		out = append(out, [2]string{k, v})
	}
	return out
}

// ---------------------------------------------------------------------------
// HTTP execution — the usable surface on top of BuildRequest/NextRequest.
// The thin runtime issues the request and decodes JSON; everything wire-shaped
// is decided declaratively by the binding.
// ---------------------------------------------------------------------------

func fullURL(br BuiltRequest) string {
	if len(br.Query) == 0 {
		return br.URL
	}
	parts := make([]string, len(br.Query))
	for i, kv := range br.Query {
		parts[i] = url.QueryEscape(kv[0]) + "=" + url.QueryEscape(kv[1])
	}
	return br.URL + "?" + strings.Join(parts, "&")
}

func doRequest(client *http.Client, br BuiltRequest) (map[string]any, http.Header, error) {
	var body io.Reader
	if br.Body != nil {
		body = strings.NewReader(*br.Body)
	}
	req, err := http.NewRequest(br.Method, fullURL(br), body)
	if err != nil {
		return nil, nil, err
	}
	for k, v := range br.Headers {
		req.Header.Set(k, v)
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, nil, err
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, resp.Header, err
	}
	if resp.StatusCode >= 400 {
		return nil, resp.Header, fmt.Errorf("%s %s: HTTP %d: %s", br.Method, br.URL, resp.StatusCode, string(raw))
	}
	var parsed map[string]any
	if len(raw) > 0 {
		if err := json.Unmarshal(raw, &parsed); err != nil {
			return nil, resp.Header, err
		}
	}
	return parsed, resp.Header, nil
}

func lowerHeaders(h http.Header) map[string]string {
	m := make(map[string]string, len(h))
	for k := range h {
		m[strings.ToLower(k)] = h.Get(k)
	}
	return m
}

// ExecuteWith issues a single action request and returns the decoded body
// (unwrapped if the action declares an unwrap key).
func ExecuteWith(client *http.Client, conn *ConnectorB, action string, args map[string]any, cred string) (any, error) {
	if client == nil {
		client = http.DefaultClient
	}
	data, _, err := doRequest(client, BuildRequest(conn, action, args, cred))
	if err != nil {
		return nil, err
	}
	if a := conn.Actions[action]; a.Unwrap != nil {
		return data[*a.Unwrap], nil
	}
	return data, nil
}

// PaginateWith walks every page of a paginated action, returning all items. The
// binding's pagination kind drives cursor extraction; the runtime just loops.
func PaginateWith(client *http.Client, conn *ConnectorB, action string, args map[string]any, cred string) ([]any, error) {
	if client == nil {
		client = http.DefaultClient
	}
	a := conn.Actions[action]
	var all []any
	br := BuildRequest(conn, action, args, cred)
	next := &br
	for next != nil {
		data, headers, err := doRequest(client, *next)
		if err != nil {
			return all, err
		}
		var items []any
		if a.Unwrap != nil {
			items, _ = data[*a.Unwrap].([]any)
		} else if a.Pagination.ItemsField != nil {
			items, _ = data[*a.Pagination.ItemsField].([]any)
		}
		all = append(all, items...)
		next = NextRequest(conn, action, args, cred, data, lowerHeaders(headers))
	}
	return all, nil
}
