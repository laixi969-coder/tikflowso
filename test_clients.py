import io
import json
import os
import unittest
from unittest.mock import patch

import cli


class ClientsTests(unittest.TestCase):
    def test_mcp_initialization_catalog_and_query(self):
        messages = [{"id": 1, "method": "initialize"},
                    {"method": "notifications/initialized"},
                    {"id": 2, "method": "tools/list"},
                    {"id": 3, "method": "tools/call", "params": {
                        "name": "detail", "arguments": {"kind": "products", "id": "p01", "market": "US"}}}]
        stream = "\n".join(json.dumps({"jsonrpc": "2.0", **m}) for m in messages)
        with patch("sys.stdin", io.StringIO(stream)), patch("sys.stdout", new_callable=io.StringIO) as result, \
             patch("cli.query", return_value={"id": "p01"}) as upstream:
            cli.mcp()
            replies = [json.loads(line) for line in result.getvalue().splitlines()]
        self.assertEqual([r["id"] for r in replies], [1, 2, 3])
        self.assertEqual({tool["name"] for tool in replies[1]["result"]["tools"]}, {"markets","meta","overview","rankings","detail","trends","trend-study"})
        self.assertEqual(json.loads(replies[2]["result"]["content"][0]["text"]), {"id": "p01"})
        upstream.assert_called_once_with("detail", {"kind": "products", "id": "p01", "market": "US"})

    def test_rejects_unnecessary_network_calls(self):
        with self.assertRaises(ValueError):
            cli.tool_result({"name": "rankings", "arguments": {"page": True}})
        with patch.dict(os.environ, {"TIKFLOWSO_API_KEY": "fixture", "TIKFLOWSO_URL": "http://example.org"}):
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                cli.query("meta", {})


if __name__ == "__main__":
    unittest.main()
