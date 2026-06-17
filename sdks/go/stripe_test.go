package toolsconnector

import (
	"io"
	"net/http"
	"net/url"
	"strings"
	"testing"
)

// mockTransport records every request and returns canned Stripe responses, the
// Go sibling of the TS e2e's mock fetch / Python's httpx.MockTransport.
type mockTransport struct {
	reqs   []*http.Request
	bodies []string
}

func (m *mockTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	var body string
	if req.Body != nil {
		b, _ := io.ReadAll(req.Body)
		body = string(b)
	}
	m.reqs = append(m.reqs, req)
	m.bodies = append(m.bodies, body)

	var resp string
	switch {
	case req.Method == "POST" && req.URL.Path == "/v1/customers":
		resp = `{"id":"cus_new","object":"customer"}`
	case req.Method == "GET" && req.URL.Path == "/v1/customers":
		if req.URL.Query().Get("starting_after") == "cus_2" {
			resp = `{"data":[{"id":"cus_3"}],"has_more":false}`
		} else {
			resp = `{"data":[{"id":"cus_1"},{"id":"cus_2"}],"has_more":true}`
		}
	default:
		resp = `{}`
	}
	return &http.Response{
		StatusCode: 200,
		Body:       io.NopCloser(strings.NewReader(resp)),
		Header:     make(http.Header),
	}, nil
}

func strp(s string) *string { return &s }
func intp(i int) *int       { return &i }

// TestStripeE2E exercises the generated Stripe client end-to-end against a mock
// transport: typed create, MAP-param flattening, cursor pagination traversal,
// and escape-hatch delegation.
func TestStripeE2E(t *testing.T) {
	mock := &mockTransport{}
	client := &http.Client{Transport: mock}
	s := NewStripe("sk_test_x", StripeWithHTTPClient(client))

	// 1 + 2: typed create + MAP-style metadata flattened into the form body.
	if _, err := s.CreateCustomer(StripeCreateCustomerArgs{
		Email:    strp("a@b.com"),
		Metadata: map[string]string{"plan": "pro"},
	}); err != nil {
		t.Fatalf("CreateCustomer: %v", err)
	}
	if mock.reqs[0].Method != "POST" || mock.reqs[0].URL.Path != "/v1/customers" {
		t.Errorf("check1: expected POST /v1/customers, got %s %s", mock.reqs[0].Method, mock.reqs[0].URL.Path)
	} else {
		t.Log("PASS  CreateCustomer -> POST /v1/customers")
	}
	form, _ := url.ParseQuery(mock.bodies[0])
	if form.Get("metadata[plan]") != "pro" {
		t.Errorf("check2: metadata not flattened: body=%q", mock.bodies[0])
	} else {
		t.Log("PASS  metadata flattened into body (metadata[plan]=pro)")
	}

	// 3 + 4 + 5: paginate walks every page; cursor = last id of the prior page.
	mock.reqs, mock.bodies = nil, nil
	items, err := s.ListCustomersAll(StripeListCustomersArgs{Limit: intp(2)})
	if err != nil {
		t.Fatalf("ListCustomersAll: %v", err)
	}
	if len(items) != 3 {
		t.Errorf("check3: expected 3 items, got %d", len(items))
	} else {
		t.Log("PASS  paginate walked every page (got 3 items)")
	}
	if len(mock.reqs) != 2 {
		t.Errorf("check4: expected 2 requests, got %d", len(mock.reqs))
	} else {
		t.Log("PASS  made exactly 2 requests")
	}
	if got := mock.reqs[1].URL.Query().Get("starting_after"); got != "cus_2" {
		t.Errorf("check5: expected starting_after=cus_2, got %q", got)
	} else {
		t.Log("PASS  page 2 cursor = last id (starting_after=cus_2)")
	}

	// 6: escape-hatch action delegates to a registered override.
	ran := false
	s2 := NewStripe("sk_test_x", StripeWithOverride("cancel_subscription",
		func(cred string, args map[string]any) (any, error) {
			ran = true
			return map[string]any{"status": "canceled"}, nil
		}))
	if _, err := s2.CancelSubscription(map[string]any{"subscription_id": "sub_1"}); err != nil {
		t.Fatalf("CancelSubscription: %v", err)
	}
	if !ran {
		t.Errorf("check6: override did not run")
	} else {
		t.Log("PASS  CancelSubscription -> override ran")
	}
}
