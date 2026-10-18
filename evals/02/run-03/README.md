# 修正後の新規holdout評価

- 参照: `nanaism/yomiyasu` v2.0.1、commit `84e1f5b15e497538fcfe19ab7e9c6f6d138f19ff`
- 候補: `47b81294f79053ba1d8fd713aa3fa788a5ba4879`、実行本文 `candidate-SKILL.md`、SHA-256 `06dbf8cee9abaeb33c457363249095d19280514cd62f228b0467faa78056fcf2`
- シナリオは [`../scenario.json`](../scenario.json)、実行前に候補修正より先に固定したハッシュは [`../manifest.json`](../manifest.json) に記録
- 各条件で新しい独立実行役1名が1回実行し、別の新しい採点者2名が匿名A/Bを順序反転して採点
- 採点1は A=参照、B=候補。採点2は A=候補、B=参照
- 実行モデル名、tool_uses、duration_msは取得できずN/A

## 結果

- 初回の匿名採点では、両条件とも全要件合格と記録された。しかしレビューで候補出力から「市民講座」が落ち、どの会場変更か単独では特定できない点が見つかった。R1は会場変更の対象を含むため、候補のR1はpartial、critical合格は不成立と訂正する。参照出力は「市民講座の会場」を明記している。訂正の根拠は [`review-adjudication-01.json`](review-adjudication-01.json) に記録し、元の出力と採点JSONは監査用に変更せず保存する。
- これにより、この候補出力を全要件合格または参照版より優位とする結論は撤回する。1件のholdoutでの結果に限り、一般的な優劣は主張しない。

生の出力・匿名採点・実行役の申告はこのディレクトリに保存。
