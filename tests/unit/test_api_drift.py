"""Unit tests for scripts/check_api_drift.py -- fully offline, no network.

Done-when: mutate a baseline (drop a scope, rename a method, add a param) and
assert the differ names EXACTLY those changes.
"""

from __future__ import annotations

import copy
import pathlib
import sys

# check_api_drift.py lives in scripts/ (not an installed package).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))

import check_api_drift as drift  # noqa: E402

TASKS = "https://www.googleapis.com/auth/tasks"
TASKS_RO = "https://www.googleapis.com/auth/tasks.readonly"

# A miniature Discovery Document with the real shape: nested resources, methods
# with id/path/httpMethod/scopes/parameters, and schemas with properties.
RAW = {
    "id": "tasks:v1",
    "name": "tasks",
    "version": "v1",
    "revision": "20260728",
    "resources": {
        "tasks": {
            "methods": {
                "list": {
                    "id": "tasks.tasks.list",
                    "path": "tasks/v1/lists/{tasklist}/tasks",
                    "httpMethod": "GET",
                    "scopes": [TASKS, TASKS_RO],
                    "parameters": {
                        "tasklist": {"type": "string", "location": "path", "required": True},
                        "maxResults": {"type": "integer", "location": "query"},
                    },
                },
                "insert": {
                    "id": "tasks.tasks.insert",
                    "path": "tasks/v1/lists/{tasklist}/tasks",
                    "httpMethod": "POST",
                    "scopes": [TASKS],
                    "parameters": {
                        "tasklist": {"type": "string", "location": "path", "required": True}
                    },
                },
            },
            "resources": {  # nested resource -- must be collected recursively
                "sub": {
                    "methods": {
                        "ping": {
                            "id": "tasks.tasks.sub.ping",
                            "path": "p",
                            "httpMethod": "GET",
                            "scopes": [],
                            "parameters": {},
                        }
                    }
                }
            },
        }
    },
    "schemas": {"Task": {"properties": {"title": {}, "id": {}, "status": {}}}},
}


def test_normalize_flattens_and_strips():
    snap = drift.normalize(RAW)
    assert snap["revision"] == "20260728"
    assert snap["version"] == "v1"
    # nested method collected recursively
    assert "tasks.tasks.sub.ping" in snap["methods"]
    # required flag preserved, scopes sorted
    assert snap["methods"]["tasks.tasks.list"]["parameters"]["tasklist"]["required"] is True
    assert snap["methods"]["tasks.tasks.list"]["scopes"] == sorted([TASKS, TASKS_RO])
    # schema fields sorted
    assert snap["schemas"]["Task"] == ["id", "status", "title"]
    # API-level scope union
    assert snap["scopes"] == sorted([TASKS, TASKS_RO])


def _mutated_raw():
    """RAW with: list drops a scope + gains a param; insert renamed to create."""
    raw_new = copy.deepcopy(RAW)
    methods = raw_new["resources"]["tasks"]["methods"]
    methods["list"]["scopes"].remove(TASKS_RO)  # drop a scope
    methods["list"]["parameters"]["pageToken"] = {
        "type": "string",
        "location": "query",
    }  # add a param
    methods["create"] = methods.pop("insert")  # rename insert -> create
    methods["create"]["id"] = "tasks.tasks.create"
    return raw_new


def test_diff_names_exactly_the_mutations():
    baseline = drift.normalize(RAW)
    new = drift.normalize(_mutated_raw())

    report = drift.diff(baseline, new)

    assert report["methods_added"] == ["tasks.tasks.create"]
    assert report["methods_removed"] == ["tasks.tasks.insert"]
    assert set(report["methods_changed"]) == {"tasks.tasks.list"}
    changed = report["methods_changed"]["tasks.tasks.list"]
    assert changed["params_added"] == ["pageToken"]
    assert changed["scopes_removed"] == [TASKS_RO]
    # API-level scope union also lost tasks.readonly
    assert report["scopes_removed"] == [TASKS_RO]
    assert drift.has_semantic_drift(report) is True


def test_revision_bump_alone_is_not_drift():
    baseline = drift.normalize(RAW)
    new = copy.deepcopy(baseline)
    new["revision"] = "20260801"
    report = drift.diff(baseline, new)
    assert report["revision_change"] == ["20260728", "20260801"]
    assert drift.has_semantic_drift(report) is False


def test_impact_flags_used_scope_only():
    baseline = drift.normalize(RAW)
    new = drift.normalize(_mutated_raw())
    report = drift.diff(baseline, new)

    # tasks.readonly IS one we declare -> HIGH
    impact_used = drift.assess_impact(report, [TASKS, TASKS_RO])
    assert any(f["level"] == "HIGH" and TASKS_RO in f["message"] for f in impact_used)

    # if we don't declare tasks.readonly, its removal is not a HIGH for us
    impact_unused = drift.assess_impact(report, [TASKS])
    assert not any(f["level"] == "HIGH" and TASKS_RO in f["message"] for f in impact_unused)


if __name__ == "__main__":
    # Allow running without pytest: python3 tests/unit/test_api_drift.py
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
