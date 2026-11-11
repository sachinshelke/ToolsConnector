"""Cross-connector pagination walks, one representative action per connector.

Every connector here used to hand back ``has_more=True`` without a working way
to fetch the next page. Either ``_fetch_next`` was never assigned, so
``anext_page()`` returned ``None`` and ``collect()`` stopped at page one, or it
called the sync action wrapper and ``anext_page()`` raised ``TypeError``.

Each case mocks two real HTTP pages through respx and checks that:

* ``anext_page()`` returns page two (not ``None``, not an exception),
* page two ends the walk (``has_more`` False, ``anext_page()`` is ``None``),
* the follow-up request carries the cursor **and** the caller's original
  filters. A fetcher that drops a filter silently pages a different result set.

Connectors with their own test module (slack, gmail, linear, notion, jira,
hubspot, calendly, confluence, okta, odoo) are covered there instead.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx
import pytest
import respx

from toolsconnector.connectors.asana import Asana
from toolsconnector.connectors.auth0 import Auth0
from toolsconnector.connectors.cloudflare import Cloudflare
from toolsconnector.connectors.dockerhub import DockerHub
from toolsconnector.connectors.figma import Figma
from toolsconnector.connectors.freshdesk import Freshdesk
from toolsconnector.connectors.gcalendar import GoogleCalendar
from toolsconnector.connectors.gdrive import GoogleDrive
from toolsconnector.connectors.gitlab import GitLab
from toolsconnector.connectors.gtasks import GoogleTasks
from toolsconnector.connectors.intercom import Intercom
from toolsconnector.connectors.linkedin import LinkedIn
from toolsconnector.connectors.mailchimp import Mailchimp
from toolsconnector.connectors.mongodb import MongoDB
from toolsconnector.connectors.openai_connector import OpenAI
from toolsconnector.connectors.outlook import Outlook
from toolsconnector.connectors.pagerduty import PagerDuty
from toolsconnector.connectors.pinecone import Pinecone
from toolsconnector.connectors.plaid import Plaid
from toolsconnector.connectors.salesforce import Salesforce
from toolsconnector.connectors.segment import Segment
from toolsconnector.connectors.sendgrid import SendGrid
from toolsconnector.connectors.teams import Teams
from toolsconnector.connectors.vercel import Vercel
from toolsconnector.connectors.x import X
from toolsconnector.connectors.zendesk import Zendesk
from toolsconnector.errors import ValidationError


@dataclass
class Walk:
    """One two-page walk through a connector's list action."""

    id: str
    make: Callable[[], Any]
    method: str
    url: str  # regex matched against the full request URL
    page1: dict[str, Any]
    page2: dict[str, Any]
    action: str
    kwargs: dict[str, Any]
    expect_params: dict[str, str] = field(default_factory=dict)
    expect_body: dict[str, Any] = field(default_factory=dict)
    expect_path: Optional[str] = None
    headers1: dict[str, str] = field(default_factory=dict)
    headers2: dict[str, str] = field(default_factory=dict)
    setup_routes: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)


def _subset(actual: Any, expected: Any, path: str = "body") -> None:
    """Assert ``expected`` is a (recursive) subset of ``actual``."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected an object, got {actual!r}"
        for key, value in expected.items():
            assert key in actual, f"{path}.{key} missing from {actual!r}"
            _subset(actual[key], value, f"{path}.{key}")
    else:
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"


WALKS = [
    # --- previously unwired: anext_page() returned None ---------------------
    Walk(
        id="freshdesk.list_tickets",
        make=lambda: Freshdesk(credentials="fd_key:acme"),
        method="GET",
        url=r"https://acme\.freshdesk\.com/api/v2/tickets",
        page1={"json": [{"id": 1, "subject": "a"}, {"id": 2, "subject": "b"}]},
        page2={"json": [{"id": 3, "subject": "c"}]},
        action="alist_tickets",
        kwargs={"status": 2, "limit": 2},
        expect_params={"page": "2", "per_page": "2", "status": "2", "filter": "status"},
    ),
    Walk(
        id="gdrive.list_files",
        make=lambda: GoogleDrive(credentials="ya29.fake"),
        method="GET",
        url=r"https://www\.googleapis\.com/drive/v3/files",
        page1={"json": {"files": [{"id": "f1", "name": "a"}], "nextPageToken": "T2"}},
        page2={"json": {"files": [{"id": "f2", "name": "b"}]}},
        action="alist_files",
        kwargs={"page_size": 1, "folder_id": "FOLDER"},
        expect_params={
            "pageToken": "T2",
            "pageSize": "1",
            "q": "'FOLDER' in parents and trashed = false",
        },
    ),
    Walk(
        id="outlook.list_messages",
        make=lambda: Outlook(credentials="fake-graph-token"),
        method="GET",
        url=r"https://graph\.microsoft\.com/v1\.0/me/messages.*",
        page1={
            "json": {
                "value": [{"id": "m1", "subject": "a"}],
                "@odata.nextLink": (
                    "https://graph.microsoft.com/v1.0/me/messages?%24top=1&%24skip=1"
                ),
            }
        },
        page2={"json": {"value": [{"id": "m2", "subject": "b"}]}},
        action="alist_messages",
        kwargs={"limit": 1},
        expect_params={"$top": "1", "$skip": "1"},
    ),
    Walk(
        id="teams.list_chat_messages",
        make=lambda: Teams(credentials="fake-graph-token"),
        method="GET",
        url=r"https://graph\.microsoft\.com/v1\.0/chats/C1/messages.*",
        page1={
            "json": {
                "value": [{"id": "1", "body": {"content": "a"}}],
                "@odata.nextLink": (
                    "https://graph.microsoft.com/v1.0/chats/C1/messages?%24top=1&%24skiptoken=S2"
                ),
            }
        },
        page2={"json": {"value": [{"id": "2", "body": {"content": "b"}}]}},
        action="alist_chat_messages",
        kwargs={"chat_id": "C1", "limit": 1},
        expect_params={"$skiptoken": "S2"},
    ),
    Walk(
        id="asana.list_tasks",
        make=lambda: Asana(credentials="fake-pat"),
        method="GET",
        url=r"https://app\.asana\.com/api/1\.0/tasks",
        page1={"json": {"data": [{"gid": "1", "name": "t1"}], "next_page": {"offset": "OFF2"}}},
        page2={"json": {"data": [{"gid": "2", "name": "t2"}], "next_page": None}},
        action="alist_tasks",
        kwargs={"project_gid": "P1", "limit": 1},
        expect_params={"offset": "OFF2", "project": "P1", "limit": "1"},
    ),
    Walk(
        id="figma.get_team_components",
        make=lambda: Figma(credentials="figd_fake"),
        method="GET",
        url=r"https://api\.figma\.com/v1/teams/T1/components",
        page1={
            "json": {"meta": {"components": [{"key": "k1", "name": "c1"}], "cursor": {"after": 42}}}
        },
        page2={"json": {"meta": {"components": [{"key": "k2", "name": "c2"}]}}},
        action="aget_team_components",
        kwargs={"team_id": "T1", "page_size": 1},
        expect_params={"after": "42", "page_size": "1"},
    ),
    Walk(
        id="intercom.search_contacts",
        make=lambda: Intercom(credentials="fake-intercom-token"),
        method="POST",
        url=r"https://api\.intercom\.io/contacts/search",
        page1={
            "json": {
                "data": [{"id": "c1", "email": "a@acme.test"}],
                "pages": {"next": {"starting_after": "SA2"}},
            }
        },
        page2={"json": {"data": [{"id": "c2", "email": "a@acme.test"}], "pages": {}}},
        action="asearch_contacts",
        kwargs={"query": "a@acme.test"},
        expect_body={
            "pagination": {"starting_after": "SA2"},
            "query": {"field": "email", "operator": "=", "value": "a@acme.test"},
        },
    ),
    Walk(
        id="zendesk.search",
        make=lambda: Zendesk(credentials="agent@acme.test:fake-token:acme"),
        method="GET",
        url=r"https://acme\.zendesk\.com/api/v2/search\.json",
        page1={
            "json": {
                "results": [{"id": 1, "result_type": "ticket"}],
                "next_page": "https://acme.zendesk.com/api/v2/search.json?page=2",
                "count": 2,
            }
        },
        page2={
            "json": {"results": [{"id": 2, "result_type": "ticket"}], "next_page": None, "count": 2}
        },
        action="asearch",
        kwargs={"query": "type:ticket", "limit": 1},
        expect_params={"page": "2", "query": "type:ticket", "per_page": "1"},
    ),
    Walk(
        id="gcalendar.list_events",
        make=lambda: GoogleCalendar(credentials="ya29.fake"),
        method="GET",
        url=r"https://www\.googleapis\.com/calendar/v3/calendars/primary/events",
        page1={"json": {"items": [{"id": "e1", "summary": "a"}], "nextPageToken": "T2"}},
        page2={"json": {"items": [{"id": "e2", "summary": "b"}]}},
        action="alist_events",
        kwargs={"time_min": "2026-09-01T00:00:00Z", "max_results": 1},
        expect_params={"pageToken": "T2", "timeMin": "2026-09-01T00:00:00Z", "maxResults": "1"},
    ),
    Walk(
        id="gtasks.list_tasks",
        make=lambda: GoogleTasks(credentials="ya29.fake"),
        method="GET",
        url=r"https://tasks\.googleapis\.com/tasks/v1/lists/L1/tasks",
        page1={"json": {"items": [{"id": "t1", "title": "a"}], "nextPageToken": "T2"}},
        page2={"json": {"items": [{"id": "t2", "title": "b"}]}},
        action="alist_tasks",
        kwargs={"task_list_id": "L1", "due_min": "2026-09-01T00:00:00Z"},
        expect_params={"pageToken": "T2", "dueMin": "2026-09-01T00:00:00Z"},
    ),
    Walk(
        id="linkedin.list_my_posts",
        make=lambda: LinkedIn(credentials="fake-li-token"),
        method="GET",
        url=r"https://api\.linkedin\.com/rest/posts",
        page1={"json": {"elements": [{"id": "urn:li:share:1"}], "paging": {"total": 2}}},
        page2={"json": {"elements": [{"id": "urn:li:share:2"}], "paging": {"total": 2}}},
        action="alist_my_posts",
        kwargs={"author": "urn:li:person:1", "count": 1},
        expect_params={"start": "1", "author": "urn:li:person:1", "count": "1"},
    ),
    Walk(
        id="plaid.get_transactions",
        make=lambda: Plaid(credentials="fake-client-id:fake-secret"),
        method="POST",
        url=r"https://production\.plaid\.com/transactions/get",
        page1={"json": {"transactions": [{"transaction_id": "t1"}], "total_transactions": 2}},
        page2={"json": {"transactions": [{"transaction_id": "t2"}], "total_transactions": 2}},
        action="aget_transactions",
        kwargs={
            "access_token": "access-fake",
            "start_date": "2026-01-01",
            "end_date": "2026-09-01",
            "limit": 1,
        },
        expect_body={
            "access_token": "access-fake",
            "start_date": "2026-01-01",
            "end_date": "2026-09-01",
            "options": {"count": 1, "offset": 1},
        },
    ),
    Walk(
        id="auth0.list_users",
        make=lambda: Auth0(credentials="fake-cid:fake-secret:acme.auth0.test"),
        method="GET",
        url=r"https://acme\.auth0\.test/api/v2/users",
        page1={"json": {"users": [{"user_id": "u1", "email": "a@acme.test"}], "total": 2}},
        page2={"json": {"users": [{"user_id": "u2", "email": "b@acme.test"}], "total": 2}},
        action="alist_users",
        kwargs={"search": "email:*@acme.test", "limit": 1},
        expect_params={"page": "1", "per_page": "1", "q": "email:*@acme.test"},
        setup_routes=[
            (
                "POST",
                r"https://acme\.auth0\.test/oauth/token",
                {"access_token": "fake-mgmt-token", "expires_in": 86400},
            )
        ],
    ),
    Walk(
        id="x.list_mentions",
        make=lambda: X(credentials="fake-bearer"),
        method="GET",
        url=r"https://api\.x\.com/2/users/U1/mentions",
        page1={
            "json": {
                "data": [{"id": "1", "text": "a"}],
                "meta": {"next_token": "N2", "result_count": 1},
            }
        },
        page2={"json": {"data": [{"id": "2", "text": "b"}], "meta": {"result_count": 1}}},
        action="alist_mentions",
        kwargs={"user_id": "U1", "max_results": 5},
        expect_params={"pagination_token": "N2", "max_results": "5"},
    ),
    Walk(
        id="sendgrid.list_templates",
        make=lambda: SendGrid(credentials="SG.fake"),
        method="GET",
        url=r"https://api\.sendgrid\.com/v3/templates",
        page1={
            "json": {
                "result": [{"id": "t1", "name": "a"}],
                "_metadata": {
                    "next": "https://api.sendgrid.com/v3/templates?page_token=PT2&page_size=1",
                    "count": 2,
                },
            }
        },
        page2={"json": {"result": [{"id": "t2", "name": "b"}], "_metadata": {"count": 2}}},
        action="alist_templates",
        kwargs={"limit": 1},
        expect_params={"page_token": "PT2", "generations": "dynamic", "page_size": "1"},
    ),
    Walk(
        id="mongodb.find",
        make=lambda: MongoDB(credentials="fake-data-api-key"),
        method="POST",
        url=r"https://data\.mongodb-api\.com/.*/action/find",
        page1={"json": {"documents": [{"_id": 1}, {"_id": 2}]}},
        page2={"json": {"documents": [{"_id": 3}]}},
        action="afind",
        kwargs={
            "collection": "orders",
            "database": "shop",
            "filter": {"status": "open"},
            "sort": {"_id": 1},
            "limit": 2,
        },
        expect_body={
            "collection": "orders",
            "database": "shop",
            "filter": {"status": "open"},
            "sort": {"_id": 1},
            "limit": 2,
            "skip": 2,
        },
    ),
    Walk(
        id="openai_connector.list_assistants",
        make=lambda: OpenAI(credentials="sk-fake"),
        method="GET",
        url=r"https://api\.openai\.com/v1/assistants",
        page1={
            "json": {
                "data": [{"id": "asst_1", "model": "gpt-x"}],
                "has_more": True,
                "last_id": "asst_1",
            }
        },
        page2={
            "json": {
                "data": [{"id": "asst_2", "model": "gpt-x"}],
                "has_more": False,
                "last_id": "asst_2",
            }
        },
        action="alist_assistants",
        kwargs={"limit": 1},
        expect_params={"after": "asst_1", "limit": "1"},
    ),
    Walk(
        id="pinecone.list_vectors",
        make=lambda: Pinecone(credentials="pc-fake:idx-abc.svc.pinecone.io"),
        method="GET",
        url=r"https://idx-abc\.svc\.pinecone\.io/vectors/list",
        page1={"json": {"vectors": [{"id": "v1"}], "pagination": {"next": "PT2"}}},
        page2={"json": {"vectors": [{"id": "v2"}]}},
        action="alist_vectors",
        kwargs={"prefix": "doc#", "namespace": "ns", "limit": 1},
        expect_params={"paginationToken": "PT2", "prefix": "doc#", "namespace": "ns"},
    ),
    Walk(
        id="salesforce.query",
        make=lambda: Salesforce(
            credentials="fake-sf-token",
            base_url="https://acme.my.salesforce.com/services/data/v59.0",
        ),
        method="GET",
        url=r"https://acme\.my\.salesforce\.com/services/data/v59\.0/query.*",
        page1={
            "json": {
                "records": [{"Id": "1", "attributes": {"type": "Account"}}],
                "done": False,
                "nextRecordsUrl": "/services/data/v59.0/query/01gXX-2000",
                "totalSize": 2,
            }
        },
        page2={
            "json": {
                "records": [{"Id": "2", "attributes": {"type": "Account"}}],
                "done": True,
                "totalSize": 2,
            }
        },
        action="aquery",
        kwargs={"soql": "SELECT Id FROM Account"},
        expect_path="/services/data/v59.0/query/01gXX-2000",
    ),
    Walk(
        id="segment.list_sources",
        make=lambda: Segment(credentials="fake-write-key:fake-api-token"),
        method="GET",
        url=r"https://api\.segmentapis\.com/sources",
        page1={
            "json": {
                "data": {
                    "sources": [{"id": "s1", "slug": "a", "name": "a"}],
                    "pagination": {"next": "C2", "totalEntries": 2},
                }
            }
        },
        page2={
            "json": {
                "data": {
                    "sources": [{"id": "s2", "slug": "b", "name": "b"}],
                    "pagination": {"totalEntries": 2},
                }
            }
        },
        action="alist_sources",
        kwargs={"limit": 1},
        expect_params={"pagination.cursor": "C2", "pagination.count": "1"},
    ),
    # --- previously wired to the sync wrapper: anext_page() raised TypeError -
    Walk(
        id="zendesk.list_tickets",
        make=lambda: Zendesk(credentials="agent@acme.test:fake-token:acme"),
        method="GET",
        url=r"https://acme\.zendesk\.com/api/v2/tickets\.json",
        page1={
            "json": {
                "tickets": [{"id": 1, "subject": "a"}],
                "next_page": "https://acme.zendesk.com/api/v2/tickets.json?page=2",
                "count": 2,
            }
        },
        page2={"json": {"tickets": [{"id": 2, "subject": "b"}], "next_page": None, "count": 2}},
        action="alist_tickets",
        kwargs={"status": "open", "limit": 1},
        expect_params={"page": "2", "status": "open", "per_page": "1"},
    ),
    Walk(
        id="cloudflare.list_zones",
        make=lambda: Cloudflare(credentials="fake-cf-token"),
        method="GET",
        url=r"https://api\.cloudflare\.com/client/v4/zones",
        page1={
            "json": {
                "success": True,
                "result": [{"id": "z1", "name": "a.test"}],
                "result_info": {"page": 1, "total_pages": 2},
            }
        },
        page2={
            "json": {
                "success": True,
                "result": [{"id": "z2", "name": "b.test"}],
                "result_info": {"page": 2, "total_pages": 2},
            }
        },
        action="alist_zones",
        kwargs={"limit": 1},
        expect_params={"page": "2", "per_page": "1"},
    ),
    Walk(
        id="dockerhub.list_repos",
        make=lambda: DockerHub(credentials="fake-dockerhub-token"),
        method="GET",
        url=r"https://hub\.docker\.com/v2/repositories/acme/.*",
        page1={
            "json": {
                "results": [{"name": "r1", "namespace": "acme"}],
                "next": "https://hub.docker.com/v2/repositories/acme/?page=2&page_size=1",
                "count": 2,
            }
        },
        page2={
            "json": {"results": [{"name": "r2", "namespace": "acme"}], "next": None, "count": 2}
        },
        action="alist_repos",
        kwargs={"namespace": "acme", "limit": 1},
        expect_params={"page": "2", "page_size": "1"},
    ),
    Walk(
        id="gitlab.list_project_members",
        make=lambda: GitLab(credentials="glpat-fake"),
        method="GET",
        url=r"https://gitlab\.com/api/v4/projects/1/members",
        page1={"json": [{"id": 1, "username": "a", "name": "A", "access_level": 30}]},
        page2={"json": [{"id": 2, "username": "b", "name": "B", "access_level": 30}]},
        headers1={"x-next-page": "2", "x-page": "1", "x-total": "2", "x-total-pages": "2"},
        headers2={"x-next-page": "", "x-page": "2", "x-total": "2", "x-total-pages": "2"},
        action="alist_project_members",
        kwargs={"project_id": "1", "query": "a", "limit": 1},
        expect_params={"page": "2", "query": "a", "per_page": "1"},
    ),
    Walk(
        id="mailchimp.list_lists",
        make=lambda: Mailchimp(credentials="fakekey-us1"),
        method="GET",
        url=r"https://us1\.api\.mailchimp\.com/3\.0/lists",
        page1={"json": {"lists": [{"id": "l1", "name": "a"}], "total_items": 2}},
        page2={"json": {"lists": [{"id": "l2", "name": "b"}], "total_items": 2}},
        action="alist_lists",
        kwargs={"limit": 1},
        expect_params={"offset": "1", "count": "1"},
    ),
    Walk(
        id="pagerduty.list_incidents",
        make=lambda: PagerDuty(credentials="fake-pd-token"),
        method="GET",
        url=r"https://api\.pagerduty\.com/incidents",
        page1={"json": {"incidents": [{"id": "i1"}], "more": True}},
        page2={"json": {"incidents": [{"id": "i2"}], "more": False}},
        action="alist_incidents",
        kwargs={"status": "triggered", "limit": 1},
        expect_params={"offset": "1", "limit": "1", "statuses[]": "triggered"},
    ),
    Walk(
        id="vercel.list_deployments",
        make=lambda: Vercel(credentials="fake-vercel-token"),
        method="GET",
        url=r"https://api\.vercel\.com/v6/deployments",
        page1={
            "json": {
                "deployments": [{"uid": "d1"}],
                "pagination": {"count": 1, "next": 1700000000000},
            }
        },
        # A full final page (count == limit) with next=null: the old code
        # reported has_more and requested ?until=None.
        page2={"json": {"deployments": [{"uid": "d2"}], "pagination": {"count": 1, "next": None}}},
        action="alist_deployments",
        kwargs={"project_id": "P1", "limit": 1},
        expect_params={"until": "1700000000000", "projectId": "P1"},
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("walk", WALKS, ids=[w.id for w in WALKS])
async def test_anext_page_walks_to_page_two(walk: Walk) -> None:
    connector = walk.make()
    with respx.mock(assert_all_called=False) as respx_mock:
        for method, url, body in walk.setup_routes:
            respx_mock.route(method=method, url__regex=url).mock(
                return_value=httpx.Response(200, json=body)
            )
        route = respx_mock.route(method=walk.method, url__regex=walk.url).mock(
            side_effect=[
                httpx.Response(200, headers=walk.headers1, **walk.page1),
                httpx.Response(200, headers=walk.headers2, **walk.page2),
            ]
        )

        await connector._setup()
        try:
            page1 = await getattr(connector, walk.action)(**walk.kwargs)
            assert page1.has_more is True, "page one should report more results"

            page2 = await page1.anext_page()

            assert page2 is not None, "anext_page() returned None despite has_more=True"
            assert len(page2.items) == 1
            assert page2.has_more is False
            assert await page2.anext_page() is None
        finally:
            await connector._teardown()

    assert route.call_count == 2
    second = route.calls[1].request
    for key, value in walk.expect_params.items():
        assert second.url.params.get(key) == value, (
            f"page-two request {key}={second.url.params.get(key)!r}, expected {value!r} "
            f"(url: {second.url})"
        )
    if walk.expect_body:
        _subset(json.loads(second.read()), walk.expect_body)
    if walk.expect_path:
        assert second.url.path == walk.expect_path


# ---------------------------------------------------------------------------
# Cases that don't fit the two-request table
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sendgrid_list_contacts_pages_through_the_rest_of_one_response() -> None:
    """/marketing/contacts has no cursor: later pages are the rest of one response.

    They used to be discarded after the first `limit`, leaving has_more=True with
    no way to reach them. Walking now hands out the next slice with no new request.
    """
    connector = SendGrid(credentials="SG.fake")
    contacts = [{"id": f"c{i}", "email": f"c{i}@acme.test"} for i in range(1, 4)]
    with respx.mock() as respx_mock:
        route = respx_mock.get("https://api.sendgrid.com/v3/marketing/contacts").mock(
            return_value=httpx.Response(200, json={"result": contacts, "contact_count": 3})
        )
        await connector._setup()
        try:
            page1 = await connector.alist_contacts(limit=2)
            assert [c.id for c in page1.items] == ["c1", "c2"]
            assert page1.has_more is True

            collected = await page1.collect()
        finally:
            await connector._teardown()

    assert [c.id for c in collected] == ["c1", "c2", "c3"]
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_salesforce_query_rejects_next_records_url_off_the_instance() -> None:
    """nextRecordsUrl is sent to the instance with the bearer token.

    A value that isn't a /services/data/ path could retarget the request
    ("https://instance@evil.test/..." puts evil.test in the host), so it must be
    refused before any request goes out.
    """
    connector = Salesforce(
        credentials="fake-sf-token", base_url="https://acme.my.salesforce.com/services/data/v59.0"
    )
    with respx.mock(assert_all_called=False) as respx_mock:
        catch_all = respx_mock.route().mock(return_value=httpx.Response(200, json={}))
        await connector._setup()
        try:
            with pytest.raises(ValidationError):
                await connector.aquery(soql="ignored", next_records_url="@evil.test/steal")
        finally:
            await connector._teardown()

    assert catch_all.call_count == 0


@pytest.mark.asyncio
async def test_figma_list_file_versions_pages_with_before() -> None:
    """Versions page backwards via ?before=<id> taken from pagination.next_page.

    The action had no parameter to request an older page at all.
    """
    connector = Figma(credentials="figd_fake")
    next_page = "https://api.figma.com/v1/files/F1/versions?page_size=1&before=900"
    with respx.mock() as respx_mock:
        route = respx_mock.get("https://api.figma.com/v1/files/F1/versions").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "versions": [{"id": "901", "created_at": "2026-09-02T00:00:00Z"}],
                        "pagination": {"next_page": next_page},
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "versions": [{"id": "900", "created_at": "2026-09-01T00:00:00Z"}],
                        "pagination": {},
                    },
                ),
            ]
        )
        await connector._setup()
        try:
            page1 = await connector.alist_file_versions(file_key="F1", limit=1)
            assert page1.page_state.cursor == "900"
            assert page1.page_state.extra["next_page"] == next_page

            page2 = await page1.anext_page()
        finally:
            await connector._teardown()

    assert page2 is not None
    assert page2.has_more is False
    assert route.calls[1].request.url.params["before"] == "900"
    assert route.calls[1].request.url.params["page_size"] == "1"


@pytest.mark.asyncio
async def test_figma_team_components_empty_page_ends_the_walk() -> None:
    """An empty team-library page is the end, even if a cursor comes back with it."""
    connector = Figma(credentials="figd_fake")
    with respx.mock() as respx_mock:
        respx_mock.get("https://api.figma.com/v1/teams/T1/components").mock(
            return_value=httpx.Response(
                200, json={"meta": {"components": [], "cursor": {"after": 42}}}
            )
        )
        await connector._setup()
        try:
            page = await connector.aget_team_components(team_id="T1")
        finally:
            await connector._teardown()

    assert page.has_more is False
    assert await page.anext_page() is None
