"""Actions that raised ``AttributeError`` on every call before this file existed."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from toolsconnector.connectors.cloudflare import Cloudflare
from toolsconnector.connectors.mixpanel import Mixpanel
from toolsconnector.errors import NotFoundError

CF = "https://api.cloudflare.com/client/v4"


@pytest.mark.asyncio
async def test_cloudflare() -> None:
    cf = Cloudflare(credentials="t")
    await cf._setup()
    ok = {"success": True, "errors": []}
    with respx.mock() as mock:
        mock.get(f"{CF}/accounts/a/workers/scripts").mock(
            return_value=httpx.Response(200, json={**ok, "result": [{"id": "w", "etag": "e"}]})
        )
        rule = mock.post(f"{CF}/zones/z/pagerules").mock(
            return_value=httpx.Response(200, json={**ok, "result": {"id": "p"}})
        )
        mock.delete(f"{CF}/zones/z").mock(return_value=httpx.Response(200, json=ok))
        assert [w.id for w in await cf.alist_workers("a")] == ["w"]
        assert (await cf.aget_worker("a", "w")).etag == "e"
        with pytest.raises(NotFoundError):
            await cf.aget_worker("a", "missing")
        assert (await cf.acreate_page_rule("z", [{"t": 1}], [{"a": 1}])).id == "p"
        assert json.loads(rule.calls[0].request.content)["targets"] == [{"t": 1}]
        assert await cf.adelete_zone("z") is True
    await cf._teardown()


@pytest.mark.asyncio
async def test_mixpanel() -> None:
    mp = Mixpanel(credentials="u:s")
    with respx.mock() as mock:
        mock.post("https://mixpanel.com/api/query/cohorts/list").mock(
            return_value=httpx.Response(200, json=[{"id": 1}])
        )
        mock.get("https://mixpanel.com/api/query/segmentation").mock(
            return_value=httpx.Response(200, json={"data": {}})
        )
        engage = mock.post(url__startswith="https://api.mixpanel.com/engage").mock(
            side_effect=[
                httpx.Response(200, json={"status": 1}),
                httpx.Response(200, json={"status": 0, "error": "bad token"}),
            ]
        )
        assert await mp.alist_cohorts() == [{"id": 1}]
        assert await mp.aget_segmentation("e", "2026-01-01", "2026-01-02") == {"data": {}}
        assert await mp.adelete_profile("u1", "tok") is True
        assert await mp.adelete_profile("u1", "bad") is False
        sent = json.loads(engage.calls[0].request.content)[0]
        assert sent["$token"] == "tok" and sent["$distinct_id"] == "u1"
