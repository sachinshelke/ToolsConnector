package toolsconnector

import (
	"io"
	"net/http"
	"strings"
	"testing"
)

// ghMock records requests and returns canned GitHub responses, including the
// root-array list bodies and the Link rel=next header that drives LINK_FOLLOW.
type ghMock struct {
	reqs   []*http.Request
	bodies []string
}

func (m *ghMock) RoundTrip(req *http.Request) (*http.Response, error) {
	var body string
	if req.Body != nil {
		b, _ := io.ReadAll(req.Body)
		body = string(b)
	}
	m.reqs = append(m.reqs, req)
	m.bodies = append(m.bodies, body)

	h := make(http.Header)
	var resp string
	switch {
	case req.URL.Path == "/repos/octocat/hello/issues" && req.Method == "GET":
		if req.URL.Query().Get("page") == "2" {
			resp = `[{"number":3}]` // page 2: root array, no next link
		} else {
			resp = `[{"number":1},{"number":2}]` // page 1: root array
			h.Set("Link", `<https://api.github.com/repos/octocat/hello/issues?per_page=2&page=2>; rel="next"`)
		}
	case strings.HasPrefix(req.URL.Path, "/orgs/"):
		resp = `[]`
	default:
		resp = `{"id":1}`
	}
	return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(resp)), Header: h}, nil
}

// TestGithubE2E exercises the generated GitHub client: a JSON-body create, a
// conditional path_variant, LINK_FOLLOW pagination over root-array responses,
// and escape-hatch delegation.
func TestGithubE2E(t *testing.T) {
	mock := &ghMock{}
	gh := NewGithub("ghp_x", GithubWithHTTPClient(&http.Client{Transport: mock}))

	// 1: JSON-body create with an array param.
	if _, err := gh.CreateIssue(CreateIssueArgs{
		Owner: "octocat", Repo: "hello", Title: "Bug", Labels: []string{"bug"},
	}); err != nil {
		t.Fatalf("CreateIssue: %v", err)
	}
	if mock.reqs[0].Method != "POST" || mock.reqs[0].URL.Path != "/repos/octocat/hello/issues" {
		t.Errorf("check1: expected POST /repos/octocat/hello/issues, got %s %s", mock.reqs[0].Method, mock.reqs[0].URL.Path)
	} else {
		t.Log("PASS  CreateIssue -> POST /repos/octocat/hello/issues")
	}
	if !strings.Contains(mock.bodies[0], `"title":"Bug"`) || !strings.Contains(mock.bodies[0], `"labels":["bug"]`) {
		t.Errorf("check2: issue body missing title/labels: %q", mock.bodies[0])
	} else {
		t.Log("PASS  issue JSON body carries title + labels array")
	}

	// 2: conditional path_variant (org branch).
	mock.reqs, mock.bodies = nil, nil
	if _, err := gh.ListRepos(ListReposArgs{Org: strp("acme"), Limit: intp(5)}); err != nil {
		t.Fatalf("ListRepos: %v", err)
	}
	if mock.reqs[0].URL.Path != "/orgs/acme/repos" {
		t.Errorf("check3: expected /orgs/acme/repos, got %s", mock.reqs[0].URL.Path)
	} else {
		t.Log("PASS  ListRepos(org) -> /orgs/acme/repos")
	}

	// 3: LINK_FOLLOW pagination over root-array responses.
	mock.reqs, mock.bodies = nil, nil
	items, err := gh.ListIssuesAll(ListIssuesArgs{Owner: "octocat", Repo: "hello", Limit: intp(2)})
	if err != nil {
		t.Fatalf("ListIssuesAll: %v", err)
	}
	if len(items) != 3 {
		t.Errorf("check4: expected 3 items, got %d", len(items))
	} else {
		t.Log("PASS  paginate walked every page (got 3 items)")
	}
	if len(mock.reqs) != 2 {
		t.Errorf("check5: expected 2 requests, got %d", len(mock.reqs))
	} else {
		t.Log("PASS  made exactly 2 requests")
	}
	if got := mock.reqs[1].URL.Query().Get("page"); got != "2" {
		t.Errorf("check6: page 2 should follow Link rel=next (page=2), got %q", got)
	} else {
		t.Log("PASS  page 2 followed the Link rel=next URL")
	}

	// 4: escape-hatch action delegates to a registered override.
	ran := false
	gh2 := NewGithub("ghp_x", GithubWithOverride("create_gist",
		func(cred string, args map[string]any) (any, error) {
			ran = true
			return map[string]any{"id": "gist_1"}, nil
		}))
	if _, err := gh2.CreateGist(map[string]any{"files": map[string]any{"a.txt": map[string]any{"content": "hi"}}}); err != nil {
		t.Fatalf("CreateGist: %v", err)
	}
	if !ran {
		t.Errorf("check7: override did not run")
	} else {
		t.Log("PASS  CreateGist -> override ran")
	}
}
