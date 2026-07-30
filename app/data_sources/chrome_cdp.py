import json
from urllib.parse import urlparse


def find_browser_target(version_payload):
    ws = version_payload.get("webSocketDebuggerUrl") if version_payload else None
    return ws if ws else None


def load_chrome_version(http_client, cdp_endpoint):
    version_url = cdp_endpoint.rstrip("/") + "/json/version"
    try:
        response = http_client.request("GET", version_url, timeout=10)
    except Exception as exc:
        return None, f"Chrome CDP endpoint at {cdp_endpoint} is unreachable: {exc}"
    if response.status_code >= 400:
        return (
            None,
            f"Chrome CDP version endpoint at {cdp_endpoint} returned HTTP {response.status_code}",
        )
    try:
        payload = json.loads(response.content)
    except Exception as exc:
        return (
            None,
            f"Chrome CDP version endpoint at {cdp_endpoint} returned invalid JSON: {exc}",
        )
    return payload, None


def find_page_target(targets, host):
    for t in targets:
        if t.get("type") != "page" or not t.get("webSocketDebuggerUrl"):
            continue
        try:
            parsed = urlparse(t.get("url", ""))
            if parsed.hostname == host:
                return t
        except Exception:
            continue
    return None


def load_chrome_targets(http_client, cdp_endpoint):
    json_url = cdp_endpoint.rstrip("/") + "/json"
    try:
        response = http_client.request("GET", json_url, timeout=10)
    except Exception as exc:
        return None, f"Chrome CDP endpoint at {cdp_endpoint} is unreachable: {exc}"
    if response.status_code >= 400:
        return (
            None,
            f"Chrome CDP endpoint at {cdp_endpoint} returned HTTP {response.status_code}",
        )
    try:
        targets = json.loads(response.content)
    except Exception as exc:
        return (
            None,
            f"Chrome CDP endpoint at {cdp_endpoint} returned invalid JSON: {exc}",
        )
    if not isinstance(targets, list):
        return None, f"Chrome CDP endpoint at {cdp_endpoint} returned unexpected format"
    return targets, None


class ChromeCDP:
    def __init__(self, websocket_url, websocket_factory=None):
        self._id_counter = 0
        self._websocket_url = websocket_url
        self._ws = None
        self._closed = False
        if websocket_factory is None:
            import websocket

            self._ws = websocket.create_connection(websocket_url, timeout=60)
        else:
            self._ws = websocket_factory(websocket_url, timeout=60)

    def _send_command(self, method, params=None):
        self._id_counter += 1
        msg = json.dumps(
            {
                "id": self._id_counter,
                "method": method,
                "params": params or {},
            }
        )
        self._ws.send(msg)
        return self._id_counter

    def _recv_by_id(self, expected_id):
        while True:
            raw = self._ws.recv()
            reply = json.loads(raw)
            if reply.get("id") != expected_id:
                continue
            return reply

    def command(self, method, params=None):
        cmd_id = self._send_command(method, params)
        reply = self._recv_by_id(cmd_id)
        if "error" in reply:
            err = reply["error"]
            raise ValueError(f"ChromeCDP protocol error: {err.get('message', err)}")
        return reply.get("result")

    def evaluate(self, expression):
        cmd_id = self._send_command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
        reply = self._recv_by_id(cmd_id)
        if "error" in reply:
            err = reply["error"]
            raise ValueError(f"ChromeCDP protocol error: {err.get('message', err)}")
        result = reply.get("result", {})
        if result.get("exceptionDetails"):
            exc = result["exceptionDetails"]
            raise ValueError(f"JavaScript exception: {exc.get('text', exc)}")
        val = result.get("result", {}).get("value")
        if val is None and result.get("result", {}).get("type") == "undefined":
            return None
        return val

    def close(self):
        if self._ws and not self._closed:
            self._ws.close()
            self._closed = True
