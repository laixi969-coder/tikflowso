"""Bound HTTP workers and incoming file bodies before allocating their content."""
from collections import Counter
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
from threading import BoundedSemaphore, Lock
from time import monotonic

from workspace import RequestError

BODY_SLOTS = BoundedSemaphore(6)
BODY_LOCK = Lock()
BY_OWNER = Counter()


class Server(ThreadingHTTPServer):
    request_queue_size = 32

    def __init__(self, *args, **kwargs):
        self.workers = BoundedSemaphore(32)
        super().__init__(*args, **kwargs)

    def get_request(self):
        client, address = super().get_request()
        client.settimeout(15)
        return client, address

    def process_request(self, client, address):
        if not self.workers.acquire(blocking=False):
            try:
                client.settimeout(0.3)
                client.sendall(b"HTTP/1.0 503 Service Unavailable\r\nRetry-After: 2\r\nContent-Length: 0\r\n\r\n")
            except OSError:
                pass
            self.shutdown_request(client)
            return
        try:
            super().process_request(client,address)
        except BaseException:
            self.workers.release()
            raise

    def process_request_thread(self, client, address):
        try:
            super().process_request_thread(client,address)
        finally:
            self.workers.release()


@contextmanager
def admit(owner):
    if not BODY_SLOTS.acquire(blocking=False):
        raise RequestError(429,"上传名额已满，请稍后再试",2)
    try:
        with BODY_LOCK:
            if BY_OWNER[owner] >= 2:
                raise RequestError(429,"当前工作区已有文件正在上传",2)
            BY_OWNER[owner] += 1
        try:
            yield
        finally:
            with BODY_LOCK:
                BY_OWNER[owner] -= 1
                if not BY_OWNER[owner]:
                    del BY_OWNER[owner]
    finally:
        BODY_SLOTS.release()


def receive(handler, size, binary, stack):
    remaining = size
    deadline = monotonic()+90
    output = stack.enter_context(tempfile.NamedTemporaryFile(prefix="tikflowso-inbound-")) if binary else bytearray()
    try:
        while remaining:
            seconds=deadline-monotonic()
            if seconds<=0:
                raise TimeoutError
            handler.connection.settimeout(min(15,seconds))
            block=handler.rfile.read1(min(65536,remaining))
            if not block:
                raise ValueError("请求体不完整")
            if binary:
                output.write(block)
            else:
                output.extend(block)
            remaining-=len(block)
    except TimeoutError as exc:
        raise RequestError(408,"上传超时，请重新选择文件") from exc
    finally:
        handler.connection.settimeout(15)
    if binary:
        output.flush()
        return Path(output.name)
    return bytes(output)

