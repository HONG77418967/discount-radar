# Model Discount Radar (discount-radar)

English | [中文](README.md)

Daily automated scraping of **official pricing pages** from 6 model vendors/platforms, producing a discount daily report and a WeChat push draft — every entry carries the compliance trio: **timestamp + official link + disclaimer**.

> Data is auto-scraped from public pages and may lag or be wrong. Always rely on vendors' official pages for real-time prices. This is not billing advice.

## Coverage

| Vendor | Source page | Typical discount captured |
|---|---|---|
| DeepSeek | api-docs.deepseek.com | Off-peak hours: half price |
| Zhipu AI (智谱) | docs.bigmodel.cn | Off-peak coding-plan credits 50% off |
| Kimi / Moonshot | platform.kimi.com | Batch ≈ 60% of standard price |
| Alibaba Bailian (百炼) | help.aliyun.com | Batch uniformly 50% off + free credits |
| Tencent Hunyuan (混元) | cloud.tencent.com | Free resource pack (WAF fallback rendering) |
| SiliconFlow (硅基流动) | siliconflow.cn | Aggregator page, non-official reference |

## Features

- **Per-site failure isolation**: each vendor runs in its own try/except; a failure is honestly labeled "failed this run" instead of killing the report.
- **WAF challenge-page detection & attribution**: for pages like Tencent Cloud docs, the script falls back to rendering with a local browser (no identity spoofing, no CAPTCHA bypass, no retry bombing).
- **Diffable JSON snapshots**: each daily snapshot is machine-comparable; the next report auto-highlights price changes vs the previous snapshot.
- **WeChat push draft**: ≤500 chars plain text, friendly to 1-on-1 push.
- **Zero keys, zero telemetry**: Python stdlib + requests only.

## Outputs

```
data/snapshot-<date>.json      # structured snapshot, every entry has fetched_at / link / disclaimer
reports/<date>-折扣雷达日报.md  # human-readable daily report with change highlights
data/wechat-<date>.txt         # WeChat plain-text push draft (≤500 chars)
```

See [examples/daily-report-2026-10-13.md](examples/daily-report-2026-10-13.md) for a sample.

## Usage (OpenClaw skill)

1. Put this repo into your OpenClaw workspace as `skills/discount-radar/`.
2. Run: `python skills/discount-radar/scripts/fetch_discounts.py --date YYYY-MM-DD` (defaults to today).
3. Chat triggers: "discount radar / price comparison / which model is cheaper".
4. Specs: see [SKILL.md](SKILL.md) (acceptance line ≥4/6 vendors, weekly review checklist, compliance red lines).

## Data sources

[references/sources.md](references/sources.md) — official vendor domains only. No third-party mirrors, no referral links.

## License

[MIT](LICENSE)
