# 模型折扣雷达 (discount-radar)

每天自动抓取 6 家模型厂商/平台的**官方定价页**，产出带"时间戳 + 官方链接 + 免责声明"三件套的折扣日报与微信推送稿。

> 数据由脚本自动抓取公开网页生成，可能滞后或有误；一切价格与折扣以各厂商官方页面实时为准，不构成任何计费依据、优惠承诺或投资建议。

## 抓取范围

| 厂商 | 数据页 | 抓到的典型折扣点 |
|---|---|---|
| DeepSeek | api-docs.deepseek.com | 错峰时段半价 |
| 智谱AI | docs.bigmodel.cn | 非高峰时段积分 5 折 |
| Kimi/Moonshot | platform.kimi.com | Batch 价约为标准价 60% |
| 阿里云百炼 | help.aliyun.com | Batch 一律 5 折 + 新人免费额度 |
| 腾讯混元 | cloud.tencent.com | 免费资源包（WAF 兜底渲染） |
| 硅基流动 | siliconflow.cn | 聚合页比价（非官方价，仅参考） |

## 特性

- **单站失败不拖垮整报**：每家独立 try/except，失败如实标注"本次抓取失败"；
- **WAF 挑战页识别归因**：腾讯云文档站的反爬挑战页自动识别，用本机浏览器正常渲染兜底（不伪造身份、不破解验证、不重试轰炸）；
- **快照可 diff**：每日 JSON 快照机器可对比，次日报自动高亮价格变动；
- **微信推送稿**：≤500 字纯文本，适配微信一对一（不支持 markdown 表格）；
- **零密钥零遥测**：纯 Python 标准库 + requests，无任何 API key、无上报。

## 输出

```
data/snapshot-<date>.json      # 结构化快照,每条含 fetched_at/link/disclaimer
reports/<date>-折扣雷达日报.md  # 人读版日报,含与上期快照对比
data/wechat-<date>.txt         # 微信纯文本推送稿(≤500 字)
```

示例见 [examples/daily-report-2026-10-13.md](examples/daily-report-2026-10-13.md)。

## 使用（OpenClaw 技能）

1. 将本仓库放入 OpenClaw 工作区 `skills/discount-radar/`；
2. 运行：`python skills/discount-radar/scripts/fetch_discounts.py --date YYYY-MM-DD`（缺省当天）；
3. 触发词：对话里说"折扣雷达 / 比价 / 哪家便宜 / 模型价格日报"；
4. 规范详见 [SKILL.md](SKILL.md)（验收线 ≥4/6 家、每周人工审核清单、合规红线）。

## 数据源清单

见 [references/sources.md](references/sources.md)——全部为厂商官方域名，禁止第三方转载链接与任何返佣链接。

## License

[MIT](LICENSE)
