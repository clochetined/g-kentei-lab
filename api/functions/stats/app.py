"""集計の読み出し API。

GET /v1/stats   全体・分野別・問題別の集計
GET /v1/health  死活確認
"""

from boto3.dynamodb.conditions import Key
from gk_common import ApiError, handle, response, table

CACHE_HEADERS = {"Cache-Control": "public, max-age=60"}


def _query_all(pk):
    items = []
    kwargs = {"KeyConditionExpression": Key("PK").eq(pk)}
    while True:
        res = table().query(**kwargs)
        items.extend(res.get("Items", []))
        if "LastEvaluatedKey" not in res:
            return items
        kwargs["ExclusiveStartKey"] = res["LastEvaluatedKey"]


def _pct(ok, n):
    return round(int(ok) * 100 / int(n)) if n else None


def get_stats():
    stats_items = _query_all("STATS")
    q_items = _query_all("QSTAT")

    global_item = {}
    cats = {}
    for it in stats_items:
        sk = it["SK"]
        if sk == "GLOBAL":
            global_item = it
        elif sk.startswith("CAT#"):
            n, ok = int(it.get("n", 0)), int(it.get("ok", 0))
            cats[sk[4:]] = {"n": n, "ok": ok, "pct": _pct(ok, n)}

    mock_count = int(global_item.get("mockCount", 0))
    practice_count = int(global_item.get("practiceCount", 0))
    body = {
        "global": {
            "mockCount": mock_count,
            "mockAvgPct": round(int(global_item.get("mockSumPct", 0)) / mock_count) if mock_count else None,
            "practiceCount": practice_count,
            "answered": int(global_item.get("answered", 0)),
            "correct": int(global_item.get("correct", 0)),
        },
        "cats": cats,
        "questions": {
            it["SK"]: {"a": int(it.get("a", 0)), "c": int(it.get("c", 0)), "pct": _pct(it.get("c", 0), it.get("a", 0))}
            for it in q_items
        },
    }
    return response(200, body, CACHE_HEADERS)


@handle
def handler(event, context):
    path = (event.get("rawPath") or event.get("path") or "").rstrip("/")
    if path.endswith("/health"):
        return response(200, {"ok": True})
    if path.endswith("/stats"):
        return get_stats()
    raise ApiError(404, "not found")
