# -*- coding: utf-8 -*-
"""build_pub.py が生成した index.html（Artifact 用の断片）を、完全な HTML 文書として書き出す。

使い方: python src/make_standalone.py [--out dist/index.html]
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(HERE, "..", "dist", "index.html")
if "--out" in sys.argv:
    out = sys.argv[sys.argv.index("--out") + 1]

html = io.open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
i = html.index("</style>") + len("</style>")
head, body = html[:i], html[i:]

HEAD = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="G検定（JDLA Deep Learning for GENERAL）対策のオリジナル問題190問、時間制限つき模擬試験、要点整理、用語集。">
<meta property="og:title" content="G検定 模試ラボ">
<meta property="og:description" content="最近の出題傾向に合わせたオリジナル問題で腕試し。9分野190問・模擬試験・要点整理・用語集。">
<meta property="og:type" content="website">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🎯</text></svg>">
"""
doc = HEAD + head + "\n</head>\n<body>" + body + "\n</body>\n</html>\n"

os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
io.open(out, "w", encoding="utf-8").write(doc)
print("wrote", os.path.abspath(out), len(doc.encode("utf-8")), "bytes")
