"""Transport for authenticated provider requests."""
from urllib import request,error
from contextvars import ContextVar
import json
import logging
import time

request_id=ContextVar("provider_parent_request",default="")
from urllib.parse import urlsplit


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def model_target(url, model):
    parts=urlsplit(url)
    if (not model or not parts.hostname or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment or (parts.scheme!="https" and not
            (parts.scheme=="http" and parts.hostname in ("localhost","127.0.0.1","::1")))):
        return ""
    return url+" "+model


def open_provider(req, timeout):
    parts = urlsplit(req.full_url)
    local = parts.hostname in ("localhost","127.0.0.1","::1")
    if (not parts.hostname or parts.username is not None or parts.password is not None
            or parts.fragment or (parts.scheme != "https" and not (local and parts.scheme == "http"))):
        raise ValueError("服务端点需要 HTTPS 或本机地址")
    handlers = [NoRedirect()]
    if local:
        handlers.append(request.ProxyHandler({}))
    started=time.monotonic()
    status=0
    vendor_id=""
    try:
        response=request.build_opener(*handlers).open(req,timeout=timeout)
        status=response.status
        vendor_id=response.headers.get("request-id") or response.headers.get("x-request-id") or ""
        return response
    except error.HTTPError as exc:
        status=exc.code
        raise
    finally:
        logging.info(json.dumps({"request_id":request_id.get(),"provider":parts.hostname,"status":status,
                                 "ms":round((time.monotonic()-started)*1000),"provider_request_id":vendor_id[:160]}))

