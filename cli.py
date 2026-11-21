"""Read a tikflowso workspace using its versioned API, or expose it over MCP stdio."""

import argparse
import json
import os
import sys
from urllib import error, parse, request


KINDS = ["products", "shops", "creators", "videos", "lives"]
COMMON = ["source", "market", "days", "date"]
TOOLS = {
    "trend-study": ("查询近 28 日采样覆盖与未来一周的同曜日基线预测。", COMMON + ["group","topic"]),
    "markets": ("按相同窗口比较各市场的成交、覆盖与活跃对象。", COMMON),
    "meta": ("列出可见的数据源、市场和数据日期。", COMMON),
    "overview": ("查询市场的成交、曝光和达人概览。", COMMON),
    "rankings": ("按对象类别和条件查询榜单。", COMMON + ["kind", "sort", "category", "segment", "q", "match", "page", "limit"]),
    "detail": ("获取对象档案、指标趋势和相关对象。", COMMON + ["kind", "id"]),
    "trends": ("汇总市场内的类目、话题、配乐、关键词或脚本。", COMMON + ["group"]),
}
CHOICES = {"kind": KINDS, "match": ["exact", "broad"], "sort": ["gmv", "sales", "views", "followers", "growth", "follower_growth"],
           "group": ["category", "tag", "music", "keyword", "script"]}
NUMBERS = {"days", "page", "limit"}


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def query(endpoint, params):
    token = os.getenv("TIKFLOWSO_API_KEY")
    if not token:
        raise ValueError("请设置环境变量 TIKFLOWSO_API_KEY。")
    base = os.getenv("TIKFLOWSO_URL", "http://127.0.0.1:8765").rstrip("/")
    target = parse.urlsplit(base)
    local = target.hostname in ("127.0.0.1", "localhost", "::1")
    if (not target.hostname or target.username or target.password or target.query or target.fragment or
            not (target.scheme == "https" or target.scheme == "http" and local)):
        raise ValueError("TIKFLOWSO_URL 须为 HTTPS 或本机 HTTP 工作区地址。")
    url = base + "/api/v1/" + endpoint
    if params:
        url += "?" + parse.urlencode(params)
    req = request.Request(url, headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    try:
        with request.build_opener(NoRedirect).open(req, timeout=15) as resp:
            return json.load(resp)
    except error.HTTPError as exc:
        try:
            message = json.load(exc).get("error")
        except (ValueError, AttributeError):
            message = None
        retry=exc.headers.get("Retry-After","") if exc.headers else ""
        wait=f" · {retry} 秒后可重试" if exc.code==429 and retry.isdigit() else ""
        raise ValueError(f"HTTP {exc.code} · {message or '工作区拒绝请求'}{wait}") from exc
    except (error.URLError, OSError, ValueError) as exc:
        raise ValueError("无法读取工作区，请检查地址和服务状态。") from exc


def schema(name, keys):
    props = {}
    for key in keys:
        value = {"type": "integer" if key in NUMBERS else "string"}
        if key in CHOICES:
            value["enum"] = CHOICES[key]
        props[key] = value
    return {"type": "object", "properties": props, "additionalProperties": False,
            "required": ["id", "kind"] if name == "detail" else []}


def tool_result(params):
    name = params.get("name")
    args = params.get("arguments", {})
    if not isinstance(name, str) or name not in TOOLS or not isinstance(args, dict):
        raise ValueError("无效的分析工具或参数。")
    spec = schema(name, TOOLS[name][1])
    if not set(spec["required"]) <= set(args) or set(args) - set(spec["properties"]):
        raise ValueError("工具参数缺失或含未知字段。")
    for key, value in args.items():
        expected = int if key in NUMBERS else str
        if type(value) is not expected or key in CHOICES and value not in CHOICES[key]:
            raise ValueError(f"无效的工具参数 {key}。")
    try:
        result = query(name, args)
        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
    except ValueError as exc:
        return {"isError": True, "content": [{"type": "text", "text": str(exc)}]}


def mcp():
    initialized = False
    for line in sys.stdin:
        reply = {"jsonrpc": "2.0", "id": None}
        try:
            msg = json.loads(line)
            if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
                raise ValueError("无效的 JSON-RPC 请求。")
            if "id" not in msg:
                continue
            reply["id"] = msg["id"]
            method, params = msg["method"], msg.get("params", {})
            if not isinstance(params, dict):
                raise ValueError("参数须为对象。")
            if method == "initialize":
                initialized = True
                reply["result"] = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                                   "serverInfo": {"name": "tikflowso", "version": "1.0.0"}}
            elif method == "ping":
                reply["result"] = {}
            elif not initialized:
                reply["error"] = {"code": -32002, "message": "尚未初始化"}
            elif method == "tools/list":
                reply["result"] = {"tools": [{"name": name, "description": item[0], "inputSchema": schema(name, item[1]),
                                              "annotations": {"readOnlyHint": True}} for name, item in TOOLS.items()]}
            elif method == "tools/call":
                reply["result"] = tool_result(params)
            else:
                reply["error"] = {"code": -32601, "message": "未知方法"}
        except json.JSONDecodeError:
            reply["error"] = {"code": -32700, "message": "无效的 JSON"}
        except ValueError as exc:
            reply["error"] = {"code": -32602, "message": str(exc)}
        print(json.dumps(reply, ensure_ascii=False), flush=True)


def main():
    import settings
    settings.load()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="endpoint", required=True)
    sub.add_parser("mcp", help="在标准输入输出上运行只读 MCP 服务")
    for name, (desc, keys) in TOOLS.items():
        cmd = sub.add_parser(name, help=desc)
        for key in keys:
            cmd.add_argument("--" + key, type=int if key in NUMBERS else str, choices=CHOICES.get(key),
                             required=name == "detail" and key in ("kind", "id"))
    args = vars(parser.parse_args())
    endpoint = args.pop("endpoint")
    if endpoint == "mcp":
        mcp()
    else:
        try:
            result = query(endpoint, {k: v for k, v in args.items() if v is not None})
        except ValueError as exc:
            parser.exit(1, str(exc) + "\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
