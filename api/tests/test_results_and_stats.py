from conftest import body_of, make_event


def mock_result(result_id="result-0001", **over):
    body = {
        "resultId": result_id,
        "clientId": "client-abc123",
        "kind": "mock",
        "n": 4,
        "correct": 3,
        "sec": 600,
        "byCat": {"cv": {"n": 2, "ok": 2}, "law": {"n": 2, "ok": 1}},
        "answers": [
            {"id": "cv-aaaaaa", "ok": True},
            {"id": "cv-bbbbbb", "ok": True},
            {"id": "law-cccccc", "ok": True},
            {"id": "law-dddddd", "ok": False},
        ],
    }
    body.update(over)
    return body


def post(handlers, body):
    return handlers["results"](make_event("POST", "/v1/results", body), None)


def stats(handlers):
    res = handlers["stats"](make_event("GET", "/v1/stats"), None)
    assert res["statusCode"] == 200
    return body_of(res)


def test_health(handlers):
    res = handlers["stats"](make_event("GET", "/v1/health"), None)
    assert res["statusCode"] == 200 and body_of(res) == {"ok": True}


def test_empty_stats(handlers):
    s = stats(handlers)
    assert s["global"]["mockCount"] == 0 and s["global"]["mockAvgPct"] is None
    assert s["cats"] == {} and s["questions"] == {}


def test_post_result_updates_aggregates(handlers):
    res = post(handlers, mock_result())
    assert res["statusCode"] == 201, res
    s = stats(handlers)
    assert s["global"]["mockCount"] == 1
    assert s["global"]["mockAvgPct"] == 75
    assert s["global"]["answered"] == 4 and s["global"]["correct"] == 3
    assert s["cats"]["cv"] == {"n": 2, "ok": 2, "pct": 100}
    assert s["cats"]["law"] == {"n": 2, "ok": 1, "pct": 50}
    assert s["questions"]["law-dddddd"] == {"a": 1, "c": 0, "pct": 0}
    assert s["questions"]["cv-aaaaaa"]["pct"] == 100


def test_duplicate_result_id_is_idempotent(handlers):
    assert post(handlers, mock_result("dup-000001"))["statusCode"] == 201
    res = post(handlers, mock_result("dup-000001"))
    assert res["statusCode"] == 200 and body_of(res)["duplicate"] is True
    s = stats(handlers)
    assert s["global"]["mockCount"] == 1
    assert s["questions"]["cv-aaaaaa"]["a"] == 1


def test_average_over_multiple_mocks(handlers):
    post(handlers, mock_result("m-000001", n=10, correct=5))
    post(handlers, mock_result("m-000002", n=10, correct=10))
    s = stats(handlers)
    assert s["global"]["mockCount"] == 2 and s["global"]["mockAvgPct"] == 75


def test_practice_kind_counted_separately(handlers):
    post(handlers, mock_result("p-000001", kind="practice", n=2, correct=1))
    s = stats(handlers)
    assert s["global"]["practiceCount"] == 1 and s["global"]["mockCount"] == 0


def test_stored_result_item(handlers, dynamodb):
    post(handlers, mock_result("item-0001"))
    items = dynamodb.scan()["Items"]
    stored = [i for i in items if i["PK"].startswith("RESULT#")]
    assert len(stored) == 1
    it = stored[0]
    assert it["SK"] == "item-0001" and int(it["pct"]) == 75 and "ttl" in it


def test_validation_errors(handlers):
    assert post(handlers, mock_result(kind="exam"))["statusCode"] == 400
    assert post(handlers, mock_result(n=0))["statusCode"] == 400
    assert post(handlers, mock_result(correct=5))["statusCode"] == 400  # correct > n
    assert post(handlers, mock_result(resultId="x"))["statusCode"] == 400
    assert post(handlers, mock_result(answers=[{"id": "DROP TABLE", "ok": True}]))["statusCode"] == 400
    assert post(handlers, mock_result(byCat={"cv": {"n": 1, "ok": 2}}))["statusCode"] == 400
    assert post(handlers, mock_result(byCat={"bad cat": {"n": 1, "ok": 1}}))["statusCode"] == 400
    too_many = [{"id": "cv-%06x" % i, "ok": True} for i in range(201)]
    assert post(handlers, mock_result(answers=too_many))["statusCode"] == 400


def test_duplicate_answer_ids_in_one_submission_count_once(handlers):
    body = mock_result("dupans-01", answers=[{"id": "cv-aaaaaa", "ok": True}, {"id": "cv-aaaaaa", "ok": False}])
    assert post(handlers, body)["statusCode"] == 201
    assert stats(handlers)["questions"]["cv-aaaaaa"]["a"] == 1


def test_unknown_path_is_404(handlers):
    res = handlers["stats"](make_event("GET", "/v1/nope"), None)
    assert res["statusCode"] == 404
