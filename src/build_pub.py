# -*- coding: utf-8 -*-
import json, io, os, hashlib, re
from collections import Counter
from bank import BANK, CATS
from notes import NOTES, TERMS

HERE = os.path.dirname(os.path.abspath(__file__))

def read(name):
    with io.open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()

def qid(cat, text):
    return cat + "-" + hashlib.md5(text.encode("utf-8")).hexdigest()[:6]

questions = []
seen = set()
for cat, q, choices, a, e in BANK:
    assert len(choices) == 4, q
    assert 0 <= a < 4, q
    i = qid(cat, q)
    assert i not in seen, q
    seen.add(i)
    questions.append({
        "id": i, "cat": cat, "q": q, "c": choices, "a": a, "e": e,
        "neg": bool(re.search(r"不適切|該当しない", q)),
    })

cat_ids = [c[0] for c in CATS]
for q in questions:
    assert q["cat"] in cat_ids, q["cat"]

terms = [{"id": hashlib.md5(t.encode("utf-8")).hexdigest()[:8], "t": t, "d": d, "cat": c} for t, d, c in TERMS]

# 第4回（2026-07）の分析から得た傾向（問題そのものは含めない）
TREND = {
    "exam": "第4回 G検定（2026年7月4日実施）を分析",
    "share": [
        ("cv", 18), ("ml", 12), ("math", 4), ("nlp", 14), ("law", 14), ("biz", 13), ("dl", 12), ("gen", 8), ("ai", 4),
    ],
    "formats": [
        ("「最も不適切なもの」を選ぶ問題", 32),
        ("空欄（A）（B）を埋める組み合わせ問題", 11),
        ("「あなたは…プロジェクトに参加している」型のシナリオ問題", 7),
    ],
    "themes": [
        "正則化（L1/L2）とバイアス・バリアンスの関係",
        "CNNの派生技術の区別（Dilated／Depthwise Separable／GAP／SENet／ResNet系）",
        "物体検出・セグメンテーション系モデルの整理（R-CNN系、YOLO、SSD、DeepLab、パノプティック）",
        "Transformer／BERT／ELMo／GPT の構造と学習方法の違い",
        "RNNの派生（LSTM／GRU、エルマン型／ジョルダン型、Attention）",
        "生成モデル（VAE／VQ-VAE／DCGAN／拡散モデル／Stable Diffusion）",
        "DQNの拡張（Double DQN、Dueling Network）とQ値・状態価値・行動価値",
        "個人情報保護法（要配慮個人情報、委託、開示請求、越境移転）",
        "生成AIと著作権（依拠性・類似性、著作者の判断、開発委託契約の納品物）",
        "プライバシー・バイ・デザイン、透明性、AIポリシー、ソフトロー",
        "PoCと精度保証、エッジ vs クラウド、MLOps、アジャイル",
        "評価指標の選択（適合率・再現率をコスト構造から選ぶ）",
        "軽量化（プルーニング・量子化・蒸留）、データ拡張（Cutout など）",
        "統計の基礎（二項分布、最尤法、次元の呪い、コサイン類似度）",
    ],
    "mock": {"n": 30, "minutes": 22, "weights": {"cv": 5, "ml": 3, "math": 2, "nlp": 4, "law": 4, "biz": 4, "dl": 4, "gen": 3, "ai": 1}},
}

data = {
    "cats": [{"id": i, "name": n, "desc": d} for i, n, d in CATS],
    "questions": questions,
    "notes": {k: [{"h": h, "b": b} for h, b in v] for k, v in NOTES.items()},
    "terms": terms,
    "trend": {
        "exam": TREND["exam"],
        "share": [{"cat": c, "pct": p} for c, p in TREND["share"]],
        "formats": [{"name": n, "pct": p} for n, p in TREND["formats"]],
        "themes": TREND["themes"],
        "mock": TREND["mock"],
    },
    "built": "2026-09-11",
}

print("questions:", len(questions), Counter(q["cat"] for q in questions))
print("answer positions:", Counter(q["a"] for q in questions))
print("neg:", sum(1 for q in questions if q["neg"]))
print("terms:", len(terms), " notes cats:", len(NOTES))

js = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
html = read("template_pub.html").replace("/*__DATA__*/null", js)
out = os.path.join(HERE, "index.html")
with io.open(out, "w", encoding="utf-8") as f:
    f.write(html)
print("bytes:", len(html.encode("utf-8")))
