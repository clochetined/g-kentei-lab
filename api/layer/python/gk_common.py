"""Lambda 関数で共有するユーティリティ（Lambda Layer として配布）。

- DynamoDB テーブルへのアクセス
- API Gateway (HTTP API v2) 向けのレスポンス生成
- リクエストボディの解析とバリデーション用の例外
"""

import base64
import json
import os
import re
import time
from decimal import Decimal

import boto3

TABLE_NAME = os.environ.get("TABLE_NAME", "")
SYNC_KEY_RE = re.compile(r"^[A-Za-z0-9]{12,64}$")
QUESTION_ID_RE = re.compile(r"^[a-z]{2,8}-[0-9a-f]{6}$")
CAT_RE = re.compile(r"^[a-z]{2,16}$")
CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
RESULT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

_table = None


def table():
    """DynamoDB Table リソース（コールドスタート後は再利用）。"""
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(TABLE_NAME)
    return _table


class ApiError(Exception):
    """HTTP ステータス付きのエラー。ハンドラの最上位で JSON に変換する。"""

    def __init__(self, status, message, extra=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra or {}


def _json_default(o):
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    raise TypeError("not serializable: %r" % (o,))


def response(status, body=None, headers=None):
    h = {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}
    if headers:
        h.update(headers)
    return {
        "statusCode": status,
        "headers": h,
        "body": "" if body is None else json.dumps(body, ensure_ascii=False, default=_json_default),
    }


def error_response(err):
    body = {"error": err.message}
    body.update(err.extra)
    return response(err.status, body)


def parse_json_body(event, max_bytes=256 * 1024):
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    if len(raw.encode("utf-8")) > max_bytes:
        raise ApiError(413, "request body too large")
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        raise ApiError(400, "invalid JSON body") from None
    if not isinstance(data, dict):
        raise ApiError(400, "JSON body must be an object")
    return data


def path_param(event, name):
    return (event.get("pathParameters") or {}).get(name) or ""


def http_method(event):
    return ((event.get("requestContext") or {}).get("http") or {}).get("method") or event.get("httpMethod") or ""


def now_ms():
    return int(time.time() * 1000)


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def require_int(value, name, lo, hi):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(400, "%s must be an integer" % name)
    if value < lo or value > hi:
        raise ApiError(400, "%s out of range (%d..%d)" % (name, lo, hi))
    return value


def handle(fn):
    """ハンドラをラップし、ApiError と想定外の例外を JSON レスポンスへ変換する。"""

    def wrapper(event, context):
        try:
            return fn(event, context)
        except ApiError as e:
            return error_response(e)
        except Exception as e:  # noqa: BLE001 - 最上位で必ず捕捉して 500 を返す
            print("ERROR", type(e).__name__, str(e))
            return response(500, {"error": "internal error"})

    return wrapper
