import pytest

from browser_fixture import create_fixture
from test_transport import Exchange, finish, TOKEN, ORIGIN


async def test_fixture_page_and_assets_are_loopback_only_and_not_cached():
    app = create_fixture(token=TOKEN, origin=ORIGIN)
    page = Exchange(app, method="GET")
    page.scope["path"] = "/spike"
    await finish(page)
    assert page.status == 200
    headers = dict(page.messages[0]["headers"])
    assert headers[b"cache-control"] == b"no-store"
    assert b"frame-ancestors 'none'" in headers[b"content-security-policy"]
    bad = Exchange(app, method="GET", client="192.0.2.1")
    bad.scope["path"] = "/spike"
    assert (await finish(bad)).status == 403


async def test_status_rejects_missing_capability_and_unsupported_paths():
    app = create_fixture(token=TOKEN, origin=ORIGIN)
    status = Exchange(app, method="GET")
    status.scope["path"] = "/spike/status"
    assert (await finish(status)).status == 200
    status = Exchange(app, method="GET", headers=[(b"host",b"127.0.0.1:8766")])
    status.scope["path"] = "/spike/status"
    assert (await finish(status)).status == 403
    missing = Exchange(app, method="GET")
    missing.scope["path"] = "/spike/assets/../pyproject.toml"
    assert (await finish(missing)).status == 404


async def test_fixture_read_and_draft_remain_zero_write():
    app = create_fixture(token=TOKEN, origin=ORIGIN)
    read = await finish(Exchange(app))
    assert read.events()[-1]["type"] == "run.completed"
    draft = await finish(Exchange(app, body={"user_text":"synthetic","route_mode":"draft_write"}))
    assert draft.events()[-1]["type"] == "run.completed"
    assert app.state.fixture_drafts.committed_business_writes == 0
