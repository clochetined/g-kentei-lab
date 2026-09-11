"""テスト共通のフィクスチャ。moto で DynamoDB をモックし、各関数のハンドラを読み込む。"""

import importlib
import json
import os
import sys

import boto3
import pytest
from moto import mock_aws

HERE = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.dirname(HERE)
TABLE_NAME = "g-kentei-lab-test"

# Layer と各関数のディレクトリを import パスに追加
sys.path.insert(0, os.path.join(API_DIR, "layer", "python"))

os.environ.setdefault("AWS_DEFAULT_REGION", "ap-northeast-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ["TABLE_NAME"] = TABLE_NAME


def load_handler(name):
    """functions/<name>/app.py を名前空間を分けて読み込む。"""
    path = os.path.join(API_DIR, "functions", name, "app.py")
    spec = importlib.util.spec_from_file_location("fn_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def dynamodb():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        ddb.create_table(
            TableName=TABLE_NAME,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
        )
        import gk_common

        gk_common._table = None  # モック環境のテーブルを使わせる
        yield ddb.Table(TABLE_NAME)


@pytest.fixture()
def handlers(dynamodb):
    return {
        "progress": load_handler("progress").handler,
        "results": load_handler("results").handler,
        "stats": load_handler("stats").handler,
    }


def make_event(method, path, body=None, path_params=None):
    """API Gateway HTTP API (payload v2) 形式のイベントを組み立てる。"""
    return {
        "version": "2.0",
        "rawPath": path,
        "requestContext": {"http": {"method": method, "path": path}},
        "pathParameters": path_params or {},
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }


def body_of(res):
    return json.loads(res["body"]) if res.get("body") else None
