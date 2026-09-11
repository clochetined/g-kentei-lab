"""学習記録の端末間同期 API。

  GET    /v1/progress/{syncKey}  保存済みの記録を返す（なければ 404）
  PUT    /v1/progress/{syncKey}  記録を保存する（古い updatedAt での上書きは 409）
  DELETE /v1/progress/{syncKey}  記録を削除する

syncKey は利用者のブラウザが生成する 12〜64 文字の英数字。ログイン機能を持たない代わりに、
このキーを知っている端末だけが同じ記録にアクセスできる。
"""

import time

from botocore.exceptions import ClientError
from gk_common import (
    SYNC_KEY_RE,
    ApiError,
    handle,
    http_method,
    now_ms,
    parse_json_body,
    path_param,
    require_int,
    response,
    table,
)

TTL_SECONDS = 365 * 24 * 3600  # 1 年間更新がなければ自動削除
MAX_DATA_BYTES = 200 * 1024


def _key(sync_key):
    return {"PK": "USER#" + sync_key, "SK": "PROGRESS"}


def _sync_key(event):
    key = path_param(event, "syncKey")
    if not SYNC_KEY_RE.match(key):
        raise ApiError(400, "syncKey must be 12-64 alphanumeric characters")
    return key


def get_progress(event):
    key = _sync_key(event)
    item = table().get_item(Key=_key(key)).get("Item")
    if not item:
        raise ApiError(404, "not found")
    return response(200, {"data": item.get("data"), "updatedAt": item.get("updatedAt")})


def put_progress(event):
    key = _sync_key(event)
    body = parse_json_body(event, max_bytes=MAX_DATA_BYTES + 4096)
    data = body.get("data")
    if not isinstance(data, dict):
        raise ApiError(400, "data must be an object")
    updated_at = require_int(body.get("updatedAt", 0), "updatedAt", 0, 10**14)
    now = now_ms()
    try:
        table().put_item(
            Item={
                **_key(key),
                "data": data,
                "updatedAt": updated_at,
                "savedAt": now,
                "ttl": int(time.time()) + TTL_SECONDS,
            },
            ConditionExpression="attribute_not_exists(updatedAt) OR updatedAt <= :u",
            ExpressionAttributeValues={":u": updated_at},
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        current = table().get_item(Key=_key(key)).get("Item") or {}
        raise ApiError(
            409,
            "a newer record exists",
            {"data": current.get("data"), "updatedAt": current.get("updatedAt")},
        ) from None
    return response(200, {"ok": True, "updatedAt": updated_at, "savedAt": now})


def delete_progress(event):
    key = _sync_key(event)
    table().delete_item(Key=_key(key))
    return response(204)


@handle
def handler(event, context):
    method = http_method(event)
    if method == "GET":
        return get_progress(event)
    if method == "PUT":
        return put_progress(event)
    if method == "DELETE":
        return delete_progress(event)
    raise ApiError(405, "method not allowed")
