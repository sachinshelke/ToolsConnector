// End-to-end test of the GENERATED GitHub SDK against a mock fetch: a JSON-body
// create, LINK_FOLLOW pagination over ROOT-ARRAY responses, a conditional
// path_variant, and the create_gist escape-hatch override.
//   Run:  node sdks/typescript/test/github.e2e.ts
import { GITHUB_BINDING, Github } from "../src/github.ts";
import { paginate } from "../src/runtime.ts";

const calls: { url: string; method: string; body: string | null }[] = [];

(globalThis as unknown as { fetch: unknown }).fetch = async (
  url: string,
  opts: { method: string; body?: string },
) => {
  calls.push({ url, method: opts.method, body: opts.body ?? null });
  const headers = new Map<string, string>();
  let body: unknown = {};
  if (url.includes("/issues") && opts.method === "GET") {
    if (url.includes("&page=2")) {
      body = [{ number: 3 }]; // page 2: root array, no next link
    } else {
      body = [{ number: 1 }, { number: 2 }]; // page 1: root array
      headers.set("link", '<https://api.github.com/repositories/9/issues?per_page=2&page=2>; rel="next"');
    }
  }
  return { json: async () => body, headers };
};

let fails = 0;
const check = (cond: boolean, msg: string) => {
  console.log(`  ${cond ? "PASS" : "FAIL"}  ${msg}`);
  if (!cond) fails++;
};

(async () => {
  const cred = "ghp_FAKE";
  const gh = new Github(cred, {
    overrides: {
      create_gist: async (_c: string, args: Record<string, unknown>) => ({ id: "gist_1", files: args.files }),
    },
  });

  // 1. JSON-body create with an array param
  calls.length = 0;
  await gh.createIssue({ owner: "octocat", repo: "hello", title: "Bug", labels: ["bug"] } as never);
  check(
    calls[0]?.method === "POST" && calls[0].url.endsWith("/repos/octocat/hello/issues"),
    "createIssue -> POST /repos/octocat/hello/issues",
  );
  check((calls[0]?.body ?? "").includes('"title":"Bug"') && (calls[0]?.body ?? "").includes('"labels":["bug"]'),
    "issue JSON body carries title + labels array");

  // 2. LINK_FOLLOW pagination over root-array responses
  calls.length = 0;
  const items: unknown[] = [];
  for await (const it of paginate(GITHUB_BINDING, "list_issues", { owner: "octocat", repo: "hello", limit: 2 }, cred))
    items.push(it);
  check(items.length === 3, `paginate walked every page (got ${items.length} items)`);
  check(calls.length === 2, `made exactly 2 requests (made ${calls.length})`);
  check((calls[1]?.url ?? "").includes("page=2"), "page 2 followed the Link rel=next URL");

  // 3. conditional path_variant: org branch
  calls.length = 0;
  await gh.listRepos({ org: "acme", limit: 5 } as never);
  check((calls[0]?.url ?? "").endsWith("/orgs/acme/repos?per_page=5"), "listRepos(org) -> /orgs/acme/repos");

  // 4. escape-hatch action delegates to the override
  const r = (await gh.createGist({ files: { "a.txt": { content: "hi" } } })) as { id: string };
  check(r.id === "gist_1", "createGist -> override ran");

  console.log(fails ? `\n  ${fails} E2E CHECK(S) FAILED` : "\n  ALL GITHUB E2E CHECKS PASS");
  process.exit(fails ? 1 : 0);
})();
