# 折扣雷达 · 数据来源清单(6 家)

> 2026-10-13 实测全部可稳定抓取(详见 reports/2026-10-13-技能变现折扣雷达可行性.md)。
> 各家均无公开价格 API / RSS,只能抓官方页面。快照中 `vendor` 与本表"厂商"一一对应。

| # | 厂商 | 抓取 URL | 要抓的字段 | 验证方式 |
|---|---|---|---|---|
| 1 | DeepSeek | https://api-docs.deepseek.com/quick_start/pricing | deepseek-chat / deepseek-reasoner 输入(缓存命中/未命中)、输出单价($/M);错峰折扣规则:峰值=UTC 01:00–04:00、06:00–10:00(工作日),其余时段(含周末节假日)一律半价 | 抽查 2 个模型价与官方表逐项核对;错峰时段表逐字核对 |
| 2 | 智谱AI(Coding Plan) | https://docs.bigmodel.cn/cn/coding-plan/overview.md | 套餐档位与价格(¥/月);非高峰积分 5 折规则:高峰=周一至周五 14:00–18:00(UTC+8),其余时段按基础积分 50% 抵扣 | 核对高峰时段定义与折扣率;与控制台套餐页比对 |
| 3 | 智谱AI(API 定价) | https://docs.bigmodel.cn/cn/guide/start/pricing | GLM-4.7-Flash 免费条目;缓存命中约为主价 25%;缓存存储"限时免费" | 免费条目与缓存百分比上下文核对;与 API 控制台比对 |
| 4 | Kimi/Moonshot | https://platform.kimi.com/docs/pricing/chat.md(标准价)+ https://platform.kimi.com/docs/pricing/batch.md(Batch 价);注意 HTML 总览页(/docs/pricing/chat)是 JS 渲染、无实价 | kimi-k3(¥20/¥40/¥2/¥20/¥100 每 1M tokens)、kimi-k2.7-code(-highspeed)单价;Batch 表(如 k2.7-code ¥0.78/¥3.90/¥16.20) | 抽查 1–2 个模型价与官方表核对;脚本同列对比得"Batch≈标准价 60%",需人工复核 |
| 5 | 阿里云百炼 | https://help.aliyun.com/zh/model-studio/model-pricing | Batch 调用输入输出一律 5 折;显式缓存命中按 10%、创建按 125%;新人免费额度每模型 100 万 tokens/90 天(仅北京地域) | 折扣关键词命中上下文核对;额度页 https://help.aliyun.com/zh/model-studio/new-free-quota 交叉验证 |
| 6 | 腾讯混元 | https://cloud.tencent.com/document/product/1729/97731(**有 WAF**:直抓返回挑战页,首跑标失败) | 免费资源包 100 万 tokens(1 年有效);后付费刊例价(元/百万 tokens);页面"最近更新时间"字段 | 每周人工审核时用浏览器核对本条目;免费包规则与官方活动页比对 |
| 6b | 硅基流动(聚合页) | https://siliconflow.cn/pricing | 聚合价格中心:Z-ai/DeepSeek/Kimi/Qwen/混元 各模型单价、分时段价(如混元 9–18 点 vs 夜间两档;DeepSeek 2–8 点错峰档)、免费模型条目 | **仅作比价参考,推送必须标注"聚合页,非厂商官方价"**;跨厂商价格以各家官方页为准 |

## 抓取注意

- 页面 >750KB:阿里云百炼、硅基流动——解析按关键词上下文截取,不做全表结构化;
- 智谱 Coding Plan 页为 `.md` 直读,结构最稳;Kimi 实价也在 `.md` 端点(MDX 表格组件 rows={{[...]}},单元格分隔是 `", "` 逗号+空格);
- 硅基流动取 "org/model 价格" 对(如 zai-org/GLM-5.3-Flash ¥0.80),比 JSON 探测更稳;
- 折扣关键词只做"命中"判断(错峰/半价/5 折/50%/免费额度/Batch/缓存),价格数字一律取自页面原文,禁止硬编码进脚本;
- 单站失败标"本次抓取失败",不影响其余站点;连续 3 天失败修复解析器;
- 腾讯云文档站有 WAF(挑战页特征 `window._<长随机名>=function`):仿浏览器头也拦,**不要尝试绕过**,如实标失败+每周人工核对;后续可评估浏览器自动化抓取方案。

## 合规备注

- 腾讯云:仅引用官方文档页,**禁止挂任何推广/返佣链接**;
- 所有输出逐条带"抓取时间戳 + 官方链接 + 免责声明"三件套;
- 广告标注义务(《互联网广告管理办法》)落地前需合规复核。
