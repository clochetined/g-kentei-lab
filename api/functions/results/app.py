"""演習・模擬試験の結果を受け取り、匿名の集計を更新する API。

  POST /v1/results

リクエスト例:
  {
    "resultId": "c3f1...",          # クライアント生成の一意 ID（再送しても二重集計しない）
    "clientId": "a8d2...",          # 端末ごとの匿名 ID
    "kind": "mock" | "practice",
    "n": 30, "correct": 21, "sec": 1180,
    "byCat": {"cv": {"n": 5, "ok": 4}, ...},
    "answers": [{"id": "cv-1a2b3c", "ok": true}, ...]
  }

DynamoDB の項目:
  RESULT#<yyyy-mm> / <resultId>   個別の結果（分析用、TTL 400 日）
  STATS / GLOBAL                  種別ごとの件数・スコア合計
  STATS / CAT#<cat>               分野ごとの出題数・正解数
  QSTAT / <questionId>            問題ごとの出題数・正解数
"""

import time

from botocore.exceptions import ClientError
from gk_common import (
    CAT_RE,
    CLIENT_ID_RE,
    QUESTION_ID_RE,
    RESULT_ID_RE,
    ApiError,
    handle,
    now_iso,
    parse_json_body,
    require_int,
    response,
    table,
)

KINDS = ("mock", "practice")
MAX_ANSWERS = 200
MAX_CATS = 20
RESULT_TTL_SECONDS = 400 * 24 * 3600


def _validate(body):
    result_id = body.get("resultId")
    if not isinstance(result_id, str) or not RESULT_ID_RE.match(result_id):
        raise ApiError(400, "resultId is required (8-64 chars: A-Z a-z 0-9 _ -)")
    client_id = body.get("clientId")
    if not isinstance(client_id, str) or not CLIENT_ID_RE.match(client_id):
        raise ApiError(400, "clientId is required (8-64 chars: A-Z a-z 0-9 _ -)")
    kind = body.get("kind")
    if kind not in KINDS:
        raise ApiError(400, "kind must be one of %s" % (KINDS,))
    n = require_int(body.get("n"), "n", 1, MAX_ANSWERS)
    correct = require_int(body.get("correct"), "correct", 0, n)
    sec = require_int(body.get("sec", 0), "sec", 0, 24 * 3600)

    by_cat = body.get("byCat") or {}
    if not isinstance(by_cat, dict) or len(by_cat) > MAX_CATS:
        raise ApiError(400, "byCat must be an object with at most %d entries" % MAX_CATS)
    cats = {}
    for cat, v in by_cat.items():
        if not isinstance(cat, str) or not CAT_RE.match(cat) or not isinstance(v, dict):
            raise ApiError(400, "invalid byCat entry: %r" % (cat,))
        cn = require_int(v.get("n"), "byCat.%s.n" % cat, 1, MAX_ANSWERS)
        cok = require_int(v.get("ok"), "byCat.%s.ok" % cat, 0, cn)
        cats[cat] = {"n": cn, "ok": cok}

    answers = body.get("answers") or []
    if not isinstance(answers, list) or len(answers) > MAX_ANSWERS:
        raise ApiError(400, "answers must be a list of at most %d items" % MAX_ANSWERS)
    seen = set()
    clean_answers = []
    for a in answers:
        if not isinstance(a, dict):
            raise ApiError(400, "invalid answer entry")
        qid = a.get("id")
        if not isinstance(qid, str) or not QUESTION_ID_RE.match(qid):
            raise ApiError(400, "invalid question id: %r" % (qid,))
        if qid in seen:
            continue
        seen.add(qid)
        clean_answers.append({"id": qid, "ok": bool(a.get("ok"))})

    return {
        "resultId": result_id,
        "clientId": client_id,
        "kind": kind,
        "n": n,
        "correct": correct,
        "sec": sec,
        "byCat": cats,
        "answers": clean_answers,
    }


def _store_result(r):
    """個別結果を保存。既に同じ resultId があれば False（集計をスキップ）。"""
    created = now_iso()
    try:
        table().put_item(
            Item={
                "PK": "RESULT#" + created[:7],
                "SK": r["resultId"],
                "clientId": r["clientId"],
                "kind": r["kind"],
                "n": r["n"],
                "correct": r["correct"],
                "pct": round(r["correct"] * 100 / r["n"]),
                "sec": r["sec"],
                "byCat": r["byCat"],
                "answers": r["answers"],
                "createdAt": created,
                "ttl": int(time.time()) + RESULT_TTL_SECONDS,
            },
            ConditionExpression="attribute_not_exists(PK)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise
    return True


def _update_aggregates(r):
    t = table()
    pct = round(r["correct"] * 100 / r["n"])
    t.update_item(
        Key={"PK": "STATS", "SK": "GLOBAL"},
        UpdateExpression="ADD #k :one, #s :pct, #q :n, #c :correct",
        ExpressionAttributeNames={
            "#k": r["kind"] + "Count",
            "#s": r["kind"] + "SumPct",
            "#q": "answered",
            "#c": "correct",
        },
        ExpressionAttributeValues={":one": 1, ":pct": pct, ":n": r["n"], ":correct": r["correct"]},
    )
    for cat, v in r["byCat"].items():
        t.update_item(
            Key={"PK": "STATS", "SK": "CAT#" + cat},
            UpdateExpression="ADD n :n, ok :ok",
            ExpressionAttributeValues={":n": v["n"], ":ok": v["ok"]},
        )
    for a in r["answers"]:
        t.update_item(
            Key={"PK": "QSTAT", "SK": a["id"]},
            UpdateExpression="ADD a :one, c :c",
            ExpressionAttributeValues={":one": 1, ":c": 1 if a["ok"] else 0},
        )


@handle
def handler(event, context):
    body = parse_json_body(event)
    r = _validate(body)
    if not _store_result(r):
        return response(200, {"ok": True, "duplicate": True, "resultId": r["resultId"]})
    _update_aggregates(r)
    return response(201, {"ok": True, "resultId": r["resultId"]})
