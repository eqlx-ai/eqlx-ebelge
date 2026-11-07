import asyncio
import os

import pytest

pytest.importorskip("mcp")

from mcp import Client

from eqlx_ebelge.mcp_server import build_server
from eqlx_ebelge.synthetic import demo_files


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "docs"
    r.mkdir()
    for name, data in demo_files().items():
        (r / name).write_bytes(data)
    secret = tmp_path / "outside.xml"
    secret.write_bytes(demo_files()["fatura_01.xml"])
    os.symlink(secret, r / "link_out.xml")
    return r


def call(server, name, args):
    async def go():
        async with Client(server) as c:
            return await c.call_tool(name, args)

    return asyncio.run(go())


def test_tools_are_read_only(root):
    async def go():
        async with Client(build_server(root)) as c:
            return await c.list_tools()

    tools = {t.name: t for t in asyncio.run(go()).tools}
    assert set(tools) == {"list_documents", "check", "read_invoices", "trial_balance"}
    assert all(t.annotations.read_only_hint for t in tools.values())


def test_check_through_mcp(root):
    res = call(build_server(root), "check", {})
    assert not res.is_error
    data = res.structured_content
    assert data["summary"]["invoices"] == 9  # the symlink to a file outside root is not read
    assert {f["code"] for f in data["findings"]} >= {"tax_id_check_digit", "payable", "possible_duplicate"}
    assert all(not f["source"].startswith("/") for f in data["findings"])


def test_trial_balance_and_invoices(root):
    tb = call(build_server(root), "trial_balance", {"path": "."}).structured_content
    assert tb["files"] == ["edefter_2026_10_yevmiye.xml"] and tb["rows"][0]["account"] == "100"
    inv = call(build_server(root), "read_invoices", {"path": "fatura_01.xml"}).structured_content
    assert len(inv["invoices"]) == 1 and inv["invoices"][0]["number"] == "EQX2026000000001"


@pytest.mark.parametrize("path", ["..", "../outside.xml", "/etc/passwd", "link_out.xml"])
def test_paths_outside_root_are_refused(root, path):
    res = call(build_server(root), "list_documents", {"path": path})
    assert res.is_error
