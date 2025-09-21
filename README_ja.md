# illumo-flow

宣言的な DSL と Fail-Fast 実行モデルを備えたワークフローオーケストレーション基盤です。

## 特徴
- `Flow` オーケストレータと DSL エッジ (`A >> B`, `(A & B) >> C`)
- `(context, payload)` シグネチャをとる `Node` / `FunctionNode`
- ステップ・ルーティング・ジョインバッファ・ペイロードを扱うコンテキスト名前空間
- `Routing(next, confidence, reason)` による動的ルーティング
- ETL / 分岐 / 並列ジョイン / ノード内タイムアウト / 早期停止のサンプルとスモークテスト

## セットアップ
```bash
uv venv --seed
source .venv/bin/activate
pip install -e .
```

### サンプルフローの実行
CLI から同梱サンプルを起動できます:
```bash
python -m examples linear_etl
python -m examples confidence_router
python -m examples parallel_enrichment
python -m examples node_managed_timeout
python -m examples early_stop_watchdog
```

### チュートリアル
ステップバイステップの学習は [docs/tutorial_ja.md](docs/tutorial_ja.md) （英語版は [docs/tutorial.md](docs/tutorial.md)）をご覧ください。

## テスト
```bash
pytest
```
`pyproject.toml` で `pythonpath = ["src"]` を設定しているため、`src` レイアウトでもそのままテストを実行できます。

## ドキュメント
- 設計/アーキテクチャ: [docs/flow_ja.md](docs/flow_ja.md) / 英語版 [docs/flow.md](docs/flow.md)
- コンセプト概説: [docs/concept_ja.md](docs/concept_ja.md)

## サンプル
- ノード実装: [examples/ops.py](examples/ops.py)
- DSL 定義と CLI: [examples/sample_flows.py](examples/sample_flows.py) / [examples/__main__.py](examples/__main__.py)
