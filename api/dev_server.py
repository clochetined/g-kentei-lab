"""ローカル開発用の API サーバー（AWS 不要）。

Lambda ハンドラをそのまま呼び出し、DynamoDB は moto のインメモリ実装で代替する。
`sam local start-api` の軽量版として、フロントエンドの結合確認に使う。

  pip install -r requirements-dev.txt
  python dev_server.py            # http://127.0.0.1:8787
  GK_API_BASE=http://127.0.0.1:8787 python ../src/build_pub.py

データはプロセス終了で消える。
"""

import importlib.util
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import boto3
from moto import mock_aws

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "layer", "python"))
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-northeast-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "local")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "local")
os.environ["TABLE_NAME"] = "g-kentei-lab-local"
PORT = int(os.environ.get("PORT", "8787"))


def load(name):
    spec = importlib.util.spec_from_file_location("fn_" + name, os.path.join(HERE, "functions", name, "app.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.handler


ROUTES = [
    (re.compile(r"^/v1/progress/(?P<syncKey>[^/]+)$"), ("GET", "PUT", "DELETE"), "progress"),
    (re.compile(r"^/v1/results$"), ("POST",), "results"),
    (re.compile(r"^/v1/stats$"), ("GET",), "stats"),
    (re.compile(r"^/v1/health$"), ("GET",), "stats"),
]
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, PUT, POST, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


class Handler(BaseHTTPRequestHandler):
    handlers = {}

    def _send(self, status, headers, body):
        self.send_response(status)
        for k, v in {**CORS, **headers}.items():
            self.send_header(k, v)
        data = body.encode("utf-8") if isinstance(body, str) else (body or b"")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def _dispatch(self, method):
        path = self.path.split("?")[0]
        if method == "OPTIONS":
            return self._send(204, {}, b"")
        for pat, methods, fn in ROUTES:
            m = pat.match(path)
            if not m:
                continue
            if method not in methods:
                msg = json.dumps({"error": "method not allowed"})
                return self._send(405, {"Content-Type": "application/json"}, msg)
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode("utf-8") if length else None
            event = {
                "version": "2.0",
                "rawPath": path,
                "requestContext": {"http": {"method": method, "path": path}},
                "pathParameters": m.groupdict(),
                "body": body,
                "isBase64Encoded": False,
            }
            res = self.handlers[fn](event, None)
            return self._send(res["statusCode"], res.get("headers", {}), res.get("body", ""))
        self._send(404, {"Content-Type": "application/json"}, json.dumps({"error": "not found"}))

    def do_GET(self):
        self._dispatch("GET")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_POST(self):
        self._dispatch("POST")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_OPTIONS(self):
        self._dispatch("OPTIONS")

    def log_message(self, fmt, *args):
        sys.stdout.write("%s %s\n" % (self.command, fmt % args))
        sys.stdout.flush()


def main():
    with mock_aws():
        ddb = boto3.resource("dynamodb")
        ddb.create_table(
            TableName=os.environ["TABLE_NAME"],
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
        )
        Handler.handlers = {name: load(name) for name in ("progress", "results", "stats")}
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        print("dev API listening on http://127.0.0.1:%d (in-memory DynamoDB)" % PORT, flush=True)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
