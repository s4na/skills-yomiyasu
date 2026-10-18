# 係り先修正のtargeted regression

- 対象候補: `47b81294f79053ba1d8fd713aa3fa788a5ba4879`（[`run-03/candidate-SKILL.md`](../run-03/candidate-SKILL.md) と同じ本文）
- ケース: `evals/01/scenarios.json` の `median_structural_repair`。初回から見ている調整用ケースで、holdoutではない
- 新しい実行役1名が候補スキルと依頼・原文だけを使い、1回実行。独立採点は行わず、Issue / Cause / General Fix Rule の対象だった係り先を確認

出力では「修正後に再テストする時間を確保するため」が「延期すると決めました」にかかる。再現の原因を時間確保の約束に結び直す表現はなく、影響範囲が調査中であることも残っている。初回のcritical不一致に対する回帰確認としてのみ扱い、一般性能は主張しない。
