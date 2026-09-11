from conftest import body_of, make_event

KEY = "abcDEF123456"


def test_get_missing_returns_404(handlers):
    res = handlers["progress"](make_event("GET", "/v1/progress/" + KEY, path_params={"syncKey": KEY}), None)
    assert res["statusCode"] == 404


def test_put_then_get_roundtrip(handlers):
    data = {"quiz": {"cv-1a2b3c": {"a": 1, "c": 1, "r": 1}}, "terms": {}, "mocks": []}
    res = handlers["progress"](
        make_event("PUT", "/v1/progress/" + KEY, {"data": data, "updatedAt": 1000}, {"syncKey": KEY}), None
    )
    assert res["statusCode"] == 200, res
    res = handlers["progress"](make_event("GET", "/v1/progress/" + KEY, path_params={"syncKey": KEY}), None)
    assert res["statusCode"] == 200
    b = body_of(res)
    assert b["updatedAt"] == 1000
    assert b["data"]["quiz"]["cv-1a2b3c"]["r"] == 1


def test_stale_put_is_rejected_with_current_data(handlers):
    ev = lambda ts, tag: make_event(  # noqa: E731
        "PUT", "/v1/progress/" + KEY, {"data": {"tag": tag}, "updatedAt": ts}, {"syncKey": KEY}
    )
    assert handlers["progress"](ev(2000, "newer"), None)["statusCode"] == 200
    res = handlers["progress"](ev(1000, "older"), None)
    assert res["statusCode"] == 409
    b = body_of(res)
    assert b["updatedAt"] == 2000 and b["data"]["tag"] == "newer"
    # 同じ updatedAt は上書き可（<=）
    assert handlers["progress"](ev(2000, "same"), None)["statusCode"] == 200


def test_delete(handlers):
    handlers["progress"](make_event("PUT", "/v1/progress/" + KEY, {"data": {}, "updatedAt": 1}, {"syncKey": KEY}), None)
    res = handlers["progress"](make_event("DELETE", "/v1/progress/" + KEY, path_params={"syncKey": KEY}), None)
    assert res["statusCode"] == 204
    res = handlers["progress"](make_event("GET", "/v1/progress/" + KEY, path_params={"syncKey": KEY}), None)
    assert res["statusCode"] == 404


def test_invalid_key_and_body(handlers):
    res = handlers["progress"](make_event("GET", "/v1/progress/short", path_params={"syncKey": "short"}), None)
    assert res["statusCode"] == 400
    res = handlers["progress"](
        make_event("PUT", "/v1/progress/" + KEY, {"data": "not-an-object"}, {"syncKey": KEY}), None
    )
    assert res["statusCode"] == 400
    ev = make_event("PUT", "/v1/progress/" + KEY, None, {"syncKey": KEY})
    ev["body"] = "{not json"
    assert handlers["progress"](ev, None)["statusCode"] == 400


def test_method_not_allowed(handlers):
    res = handlers["progress"](make_event("PATCH", "/v1/progress/" + KEY, path_params={"syncKey": KEY}), None)
    assert res["statusCode"] == 405
