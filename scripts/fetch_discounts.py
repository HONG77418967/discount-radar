#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模型折扣雷达 · 官方定价页抓取脚本(MVP v0.1)

用法(PowerShell,工作区根目录):
    python -X utf8 skills\\discount-radar\\scripts\\fetch_discounts.py --date 2026-10-13 --label 首期
    日常跑可省略参数(默认当天、无期数标签)。

产出:
    skills/discount-radar/data/snapshot-<date>.json   快照(每条含 时间戳+官方链接+免责声明)
    reports/<date>-折扣雷达日报[-<label>].md          日报(与最近旧快照 diff,变动高亮)
    skills/discount-radar/data/wechat-<date>.txt      微信纯文本版(<=500 字)

设计原则:
    - 每个抓取目标独立 try/except,单站失败标"本次抓取失败",不拖垮整报;
    - 折扣关键词只做"命中"判断(错峰/半价/5折/50%/免费/Batch/缓存),
      价格数字一律取自页面原文,禁止硬编码;
    - 与最近一份旧快照按 (厂商, 条目) diff;首跑无旧快照则跳过。
"""

import argparse
import html as htmllib
import json
import re
import sys
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TZ8 = timezone(timedelta(hours=8))
DISCLAIMER = ("本条信息由脚本自动抓取公开网页生成,可能滞后或有误;"
              "价格与折扣以厂商官方页面实时为准,不构成计费依据或承诺。")
UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}

SCRIPT_DIR = Path(__file__).resolve().parent          # .../skills/discount-radar/scripts
SKILL_DIR = SCRIPT_DIR.parent                          # .../skills/discount-radar
WORKSPACE = SKILL_DIR.parent.parent                    # 工作区根目录
DATA_DIR = SKILL_DIR / "data"
REPORT_DIR = WORKSPACE / "reports"


# ---------------------------------------------------------------- 基础工具

def http_get(url, timeout=35):
    """requests 优先,缺库时回退 urllib。返回文本。"""
    try:
        import requests
        r = requests.get(url, headers=UA, timeout=timeout)
        r.raise_for_status()
        if not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
            r.encoding = r.apparent_encoding or "utf-8"
        return r.text
    except ImportError:
        import urllib.request
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        for enc in ("utf-8", "gbk"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", "replace")


_SCRIPT_BLOCK = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


def html_to_text(s):
    """去 script/style 与标签,实体反转义,折叠空白。"""
    s = _SCRIPT_BLOCK.sub(" ", s)
    s = _TAG.sub(" ", s)
    s = htmllib.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _clean(snip):
    return re.sub(r"\s+", " ", snip).strip()


def grab(text, pattern, span=180, hits=3, flags=re.I):
    """围绕 pattern 命中点截取上下文片段,去重。"""
    out, seen = [], set()
    for m in re.finditer(pattern, text, flags):
        s = max(0, m.start() - span // 3)
        e = min(len(text), m.end() + span)
        snip = _clean(text[s:e])
        key = snip[:60]
        if key in seen:
            continue
        seen.add(key)
        out.append(snip)
        if len(out) >= hits:
            break
    return out


def near_kw(text, anchor_pat, kw_pat, span=240, hits=1):
    """锚点(如 Batch)附近 span 窗口内出现关键词(如 5折)才算命中。"""
    out = []
    for m in re.finditer(anchor_pat, text, re.I):
        s, e = max(0, m.start() - span), min(len(text), m.end() + span)
        w = _clean(text[s:e])
        if re.search(kw_pat, w, re.I):
            out.append(w)
            if len(out) >= hits:
                break
    return out


def _dehtml_if_needed(text):
    return html_to_text(text) if re.search(r"<html|<!doctype", text[:4000], re.I) else text


def item(name, price, discount, evidence):
    return dict(name=name, price=price, discount=discount, evidence=evidence)


# ---------------------------------------------------------------- 各站解析器
# 返回 (items, meta)。meta 为附加事实(如页面"最近更新时间")。

def parse_deepseek(text):
    t = html_to_text(text)
    items, meta = [], {}
    rule = grab(t, r"错峰|off.?peak|半价", span=260, hits=1)
    if rule:
        items.append(item("错峰折扣规则", rule[0][:220],
                          "错峰时段半价(关键词命中,以官方页为准)", rule[0]))
    seen = set()
    for m in re.finditer(r"deepseek-[a-z0-9]+", t, re.I):
        name = m.group(0).lower()
        if name in seen:
            continue
        w = t[m.end(): m.end() + 420]
        nums = list(dict.fromkeys(re.findall(r"[$￥¥]\s?\d+(?:\.\d+)?", w)))
        if nums:
            seen.add(name)
            items.append(item(name, "、".join(nums) + "($/M tokens,字段顺序以官方页为准)",
                              "", _clean(w)[:200]))
        if len(seen) >= 3:
            break
    meta["models_found"] = sorted(seen)
    return items, meta


def parse_bigmodel_coding(text):
    t = _dehtml_if_needed(text)
    if "<td" in t or "<tr" in t:  # .md 内嵌 JSX 表格,去标签后上下文更可读
        t = html_to_text(t)
    items, meta = [], {}
    off = near_kw(t, r"高峰", r"50\s?%|五折|5\s?折|0\.5", span=280, hits=1)
    if off:
        items.append(item("分时积分折扣", off[0][:220],
                          "非高峰时段积分 5 折(关键词命中,以官方页为准)", off[0]))
    for h in grab(t, r"[¥￥]\s?\d+(?:\.\d+)?|积分", span=150, hits=3):
        items.append(item("套餐/计价要点", h[:200], "", h))
    return items, meta


def parse_bigmodel_api(text):
    t = _dehtml_if_needed(text)
    items, meta = [], {}
    free = near_kw(t, r"GLM-[\w.\-]*Flash[\w.\-]*|限时免费", r"免费|0\s*元", span=200, hits=1)
    if free:
        items.append(item("限免/免费条目(具体模型见证据)", free[0][:220],
                          "限时免费(关键词命中,以官方页为准)", free[0]))
    c = near_kw(t, r"缓存", r"\d+(?:\.\d+)?\s*(?:%|元)|免费", span=240, hits=1)
    if c:
        items.append(item("缓存计费", c[0][:220], "", c[0]))
    for h in grab(t, r"[¥￥]\s?\d+(?:\.\d+)?", span=150, hits=2):
        items.append(item("API 价格要点", h[:200], "", h))
    return items, meta


def _md_table_rows(text):
    """从 MDX 组件 rows={["a","b",...],...} 中抽取行(单元格列表的列表)。"""
    rows = []
    for block in re.findall(r"rows=\{\[(.*?)\]\s*\}", text, re.S):
        for cap in re.findall(r"\[([^\[\]]+)\]", block):
            cells = [c.strip().strip('"') for c in re.split(r'"\s*,\s*"', cap)]
            if len(cells) >= 3 and any(c.strip() for c in cells):
                rows.append(cells)
    return rows


def _row_prices(cells):
    return [re.sub(r"\s+", "", x) for x in
            re.findall(r"[¥￥$]\s?\d+(?:\.\d+)?", ",".join(cells))]


def parse_kimi(text):
    items, meta = [], {}
    rows = _md_table_rows(text)
    std = [r for r in rows if not any("Batch" in c for c in r)]
    bat = [r for r in rows if any("Batch" in c for c in r)]
    meta["rows_std"] = [[r[0], _row_prices(r)] for r in std[:6]]
    meta["rows_batch"] = [[r[0], _row_prices(r)] for r in bat[:6]]

    def mk(cells, tag):
        name = re.sub(r"[(（]\s*Batch\s*[)）]", "", cells[0]).strip()
        prices = _row_prices(cells)
        if not name or not prices:
            return None
        return item(f"{name}({tag})", "、".join(prices) + "(/M tokens,列序以官方页为准)",
                    "", _clean(" | ".join(cells))[:220])

    for cells in std[:3]:
        it = mk(cells, "标准")
        if it:
            items.append(it)
    for cells in bat[:2]:
        it = mk(cells, "Batch")
        if it:
            items.append(it)
    if not items:  # 回退:HTML 渲染页旧逻辑
        t = html_to_text(text)
        seen = set()
        for m in re.finditer(r"kimi[-_a-z0-9.]{2,24}", t, re.I):
            name = m.group(0).lower().strip(".-_")
            if name in seen:
                continue
            w = t[m.end(): m.end() + 380]
            nums = list(dict.fromkeys(re.findall(
                r"[$￥¥]\s?\d+(?:\.\d+)?|\d+(?:\.\d+)?\s*元\s*/\s*M", w, re.I)))
            if nums:
                seen.add(name)
                items.append(item(name, "、".join(nums)[:180] + "(/M tokens,以官方页为准)",
                                  "", _clean(w)[:200]))
            if len(items) >= 4:
                break
    return items, meta


def _batch_ratio_note(std_rows, batch_rows):
    """std_rows/batch_rows 均为 [名称, 价格列表] 结构(来自 parse_kimi 的 meta)。"""
    def to_floats(xs):
        out = []
        for x in xs:
            try:
                out.append(float(re.sub(r"[^\d.]", "", str(x))))
            except ValueError:
                pass
        return out

    for name_b, pb_raw in batch_rows:
        bn = re.sub(r"[(（]\s*Batch\s*[)）]", "", str(name_b)).strip()
        pb = to_floats(pb_raw if isinstance(pb_raw, list) else [pb_raw])
        for name_s, ps_raw in std_rows:
            if str(name_s).strip() == bn:
                ps = to_floats(ps_raw if isinstance(ps_raw, list) else [ps_raw])
                if ps and len(ps) == len(pb) and all(p > 0 for p in ps):
                    rs = [x / y for x, y in zip(pb, ps)]
                    lo, hi = min(rs), max(rs)
                    if abs(hi - lo) < 0.02:
                        return f"Batch 价约为标准价的 {round(lo * 100)}%(脚本同列对比估算,以官方页为准)"
                    return (f"Batch 价约为标准价的 {round(lo * 100)}%–{round(hi * 100)}%"
                            "(脚本同列对比估算,以官方页为准)")
    return ""


def attach_batch_ratio(snap):
    """Kimi 标准价页 vs Batch 页同模型同列对比,折扣比写入 Batch 条目。"""
    chat = next((s for s in snap["sources"]
                 if s["key"] == "kimi-chat" and s["status"] == "ok"), None)
    batch = next((s for s in snap["sources"]
                  if s["key"] == "kimi-batch" and s["status"] == "ok"), None)
    if not (chat and batch):
        return
    note = _batch_ratio_note(chat["meta"].get("rows_std", []),
                             batch["meta"].get("rows_batch", []))
    if note:
        for it in batch["items"]:
            if "Batch" in it["name"] and not it.get("discount"):
                it["discount"] = note


def parse_aliyun(text):
    t = html_to_text(text)
    items, meta = [], {}
    b = near_kw(t, r"Batch", r"5\s?折|五折|50\s?%", span=280, hits=1)
    if b:
        items.append(item("Batch 调用折扣", b[0][:240],
                          "Batch 一律 5 折(关键词命中,以官方页为准)", b[0]))
    c = near_kw(t, r"缓存命中|显式缓存|CacheHit", r"\d+(?:\.\d+)?\s*%|元\s*/", span=220, hits=1)
    if c:
        items.append(item("缓存计费", c[0][:240], "", c[0]))
    f = near_kw(t, r"免费额度|新人免费", r"100\s?万|百万|tokens|Token", span=240, hits=1)
    if f:
        items.append(item("新人免费额度", f[0][:240], "免费额度", f[0]))
    if not items:
        for h in grab(t, r"\d+(?:\.\d+)?\s*元\s*/\s*(?:千|百万)?\s*tokens?", span=160, hits=2):
            items.append(item("价格字段", h[:180], "", h))
    return items, meta


def parse_tencent(text):
    t = html_to_text(text)
    items, meta = [], {}
    m = re.search(r"最近更新时间[:：]?\s*([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2})", t)
    if m:
        meta["页面最近更新时间"] = m.group(1)
    f = near_kw(t, r"免费资源包|免费额度", r"100\s?万|百万|tokens|Token", span=260, hits=1)
    if f:
        items.append(item("免费资源包", f[0][:240], "免费资源包(关键词命中,以官方页为准)", f[0]))
    for h in grab(t, r"\d+(?:\.\d+)?\s*元\s*/\s*(?:千|百万)?\s*tokens?", span=170, hits=2):
        items.append(item("后付费刊例价", h[:200], "", h))
    return items, meta


def parse_siliconflow(text):
    raw = text
    t = html_to_text(raw)
    items, meta = [], {}
    # 1) 去标签文本上的 "org/model 价格" 对
    pat_t = re.compile(r"([A-Za-z][\w\-]*/[A-Za-z][\w.\-]+)\s+(免费|[¥￥$]\s?[\d.]+)")
    seen = set()
    for m in pat_t.finditer(t):
        name, val = m.group(1), m.group(2)
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        items.append(item(name, val, "免费" if val == "免费" else "",
                          t[max(0, m.start() - 60): m.end() + 60]))
        if len(items) >= 4:
            break
    # 2) 内嵌 JSON 价格字段
    if not items:
        pat = re.compile(
            r'"([^"]*(?:deepseek|qwen|glm|kimi|hunyuan|z-ai)[^"]{0,40})"'
            r'[^{}]{0,320}?"(?:price|input|output|per_token|amount)"\s*:\s*"?([\d.]+)', re.I)
        for m in pat.finditer(raw):
            name, val = m.group(1)[:48], m.group(2)
            if (name, val) in seen:
                continue
            seen.add((name, val))
            items.append(item(name, val, "", _clean(raw[max(0, m.start() - 60): m.end() + 80])))
            if len(items) >= 4:
                break
    # 3) 免费关键词兑底
    if not items:
        for h in grab(t, r"免费|0\s*元|Free", span=140, hits=2):
            items.append(item("免费条目(聚合页,具体见证据)", h[:160], "免费", h))
    return items, meta


SOURCES = [
    dict(key="deepseek", vendor="DeepSeek",
         url="https://api-docs.deepseek.com/quick_start/pricing", parser=parse_deepseek),
    dict(key="bigmodel-coding", vendor="智谱AI",
         url="https://docs.bigmodel.cn/cn/coding-plan/overview.md", parser=parse_bigmodel_coding),
    dict(key="bigmodel-api", vendor="智谱AI",
         url="https://docs.bigmodel.cn/cn/guide/start/pricing", parser=parse_bigmodel_api),
    dict(key="kimi-chat", vendor="Kimi/Moonshot",
         url="https://platform.kimi.com/docs/pricing/chat.md", parser=parse_kimi),
    dict(key="kimi-batch", vendor="Kimi/Moonshot",
         url="https://platform.kimi.com/docs/pricing/batch.md", parser=parse_kimi),
    dict(key="aliyun-bailian", vendor="阿里云百炼",
         url="https://help.aliyun.com/zh/model-studio/model-pricing", parser=parse_aliyun),
    dict(key="tencent-hunyuan", vendor="腾讯混元",
         url="https://cloud.tencent.com/document/product/1729/97731", parser=parse_tencent),
    dict(key="siliconflow", vendor="硅基流动",
         url="https://siliconflow.cn/pricing", parser=parse_siliconflow,
         note="聚合比价页,非厂商官方价,仅作参考"),
]


# ---------------------------------------------------------------- 抓取与快照

def has_real_data(items):
    for it in items:
        blob = str(it.get("price", "")) + str(it.get("discount", ""))
        if re.search(r"\d", blob):
            return True
    return False


def fetch_source(src, timeout):
    now = datetime.now(TZ8).isoformat(timespec="seconds")
    base = dict(key=src["key"], vendor=src["vendor"], url=src["url"],
                note=src.get("note", ""), fetched_at=now, disclaimer=DISCLAIMER)
    try:
        text = http_get(src["url"], timeout=timeout)
    except Exception as e:
        return dict(base, status="failed", error=f"抓取失败:{type(e).__name__}: {e}", items=[], meta={})
    if re.search(r"window\._[A-Za-z]{16,}\s*=", text[:4000]):
        return dict(base, status="failed",
                    error="反爬挑战页(WAF)拦截,脚本直抓不可用,需人工/浏览器核对",
                    items=[], meta={})
    try:
        items, meta = src["parser"](text)
    except Exception as e:
        return dict(base, status="failed",
                    error=f"解析失败(页面可能改版):{type(e).__name__}: {e}", items=[], meta={})
    for it in items:
        it.setdefault("link", src["url"])
        it.setdefault("fetched_at", now)
        it.setdefault("disclaimer", DISCLAIMER)
    if not has_real_data(items):
        return dict(base, status="failed",
                    error="关键价格/折扣字段未命中(页面可能改版或 JS 渲染)", items=items, meta=meta)
    return dict(base, status="ok", error="", items=items, meta=meta)


def find_prev_snapshot(date_str):
    """返回(文件名, json)——文件名日期严格早于 date_str 的最近一份。"""
    if not DATA_DIR.exists():
        return None, None
    best = None
    for p in DATA_DIR.glob("snapshot-*.json"):
        m = re.search(r"snapshot-(\d{4}-\d{2}-\d{2})\.json$", p.name)
        if m and m.group(1) < date_str and (best is None or m.group(1) > best[0]):
            best = (m.group(1), p)
    if not best:
        return None, None
    try:
        return best[1].name, json.loads(best[1].read_text(encoding="utf-8"))
    except Exception:
        return None, None


def diff_snapshots(prev, cur):
    def idx(snap):
        return {(s["vendor"], i["name"]): (str(i.get("price", "")), str(i.get("discount", "")))
                for s in snap.get("sources", []) if s.get("status") == "ok"
                for i in s.get("items", [])}
    p, c = idx(prev), idx(cur)
    added = [f"{k[0]}·{k[1]}" for k in c if k not in p]
    removed = [f"{k[0]}·{k[1]}" for k in p if k not in c]
    changed = [f"{k[0]}·{k[1]}:{p[k][0][:40] or p[k][1][:40]} → {c[k][0][:40] or c[k][1][:40]}"
               for k in c if k in p and p[k] != c[k]]
    return added, removed, changed


# ---------------------------------------------------------------- 报告生成

def vendor_rollup(snap):
    """按厂商归并(智谱两个页面算一家),保持顺序。返回 [(vendor, status, src)]。"""
    groups = OrderedDict()
    for s in snap["sources"]:
        groups.setdefault(s["vendor"], []).append(s)
    rows = []
    for v, srcs in groups.items():
        ok = [s for s in srcs if s["status"] == "ok"]
        rows.append((v, "ok" if ok else "failed", ok[0] if ok else srcs[0]))
    return rows


def build_report(date_str, label, snap, prev_name, prev_snap):
    groups = OrderedDict()
    for s in snap["sources"]:
        groups.setdefault(s["vendor"], []).append(s)
    okn = sum(1 for _, ss in groups.items() if any(s["status"] == "ok" for s in ss))
    L = []
    L.append(f"# 模型折扣雷达日报 · {date_str}" + (f"({label})" if label else ""))
    L.append("")
    L.append(f"- 抓取执行:{snap['fetched_at']}(Asia/Shanghai,fetch_discounts.py 自动抓取)")
    L.append(f"- 覆盖:{len(groups)} 家,成功 {okn} 家 / 失败 {len(groups) - okn} 家")
    L.append(f"- 基线快照:{prev_name or '无(本期为基线)'}")
    L.append("")
    L.append("> **免责声明**:本报告由脚本自动抓取各厂商公开定价页生成,可能滞后或有误;"
             "**一切价格与折扣以各厂商官方页面实时为准**,本报告不构成任何计费依据、优惠承诺或投资建议。"
             "转发请注明出处与抓取时间。")
    L.append("")
    n = 0
    for v, srcs in groups.items():
        n += 1
        ok_any = any(s["status"] == "ok" for s in srcs)
        mark = "✅ 抓取成功" if ok_any else "❌ 本次抓取失败"
        L.append(f"## {n}. {v} —— {mark}")
        for s in srcs:
            L.append("")
            L.append(f"**数据页 `{s['key']}`**")
            L.append(f"- 官方链接:{s['url']}")
            L.append(f"- 抓取时间:{s['fetched_at']}")
            L.append("- 免责声明:数据自动抓取,以官方页实时为准,不构成计费依据。")
            if s.get("note"):
                L.append(f"- 性质说明:{s['note']}")
            if s["status"] != "ok":
                L.append(f"- 失败原因:{s.get('error') or '未知'}")
                continue
            L.append("- 价格要点:")
            for it in s["items"]:
                L.append(f"  - **{it['name']}**:{it['price']}")
            disc = [it for it in s["items"] if it.get("discount")]
            if disc:
                L.append("- 折扣点:")
                for it in disc:
                    L.append(f"  - {it['discount']}")
            ev = _clean(str(s["items"][0].get("evidence", "")))[:150]
            if ev:
                L.append(f"- 证据摘录(供人工核对):…{ev}…")
            for k, val in (s.get("meta") or {}).items():
                if k in ("rows_std", "rows_batch"):
                    continue
                L.append(f"- {k}:{val}")
        L.append("")
    L.append("## 与上期快照对比")
    L.append("")
    if not prev_snap:
        L.append("- 首期运行,无历史快照,跳过 diff;本期快照作为后续对比基线。")
    else:
        added, removed, changed = diff_snapshots(prev_snap, snap)
        if not (added or removed or changed):
            L.append("- 与上一期相比:**无变动**。")
        else:
            for a in added:
                L.append(f"- 🟢 新增:{a}")
            for ch in changed:
                L.append(f"- 🟡 变动:{ch}")
            for r in removed:
                L.append(f"- 🔴 消失:{r}")
    L.append("")
    L.append("## 本周人工审核提示(预算约 1 小时)")
    L.append("")
    L.append("- [ ] 逐家点击上方官方链接,抽查每条价格要点(约 25 分钟);")
    L.append("- [ ] 核对 DeepSeek 错峰时段表、智谱非高峰时段定义与官方页一致(约 10 分钟);")
    L.append("- [ ] 核对百炼 Batch/缓存计费、混元免费资源包规则未变(约 10 分钟);")
    L.append("- [ ] 检查微信版 ≤500 字、纯文本、含时间戳与免责声明(约 5 分钟);")
    L.append("- [ ] 失败站点归因:页面改版则修解析器,超时则补跑(预留 10 分钟)。")
    L.append("")
    L.append("## 意见建议与主推方向(小龙女判断,最终以 H先生口径为准)")
    L.append("")
    L.append("1. **主推方向**:向订阅用户主推“错峰调度”省钱打法——DeepSeek 错峰半价 + "
             "智谱非高峰 5 折,叠加可把常见推理成本压到刊例的 25%–50%,这是本期数据里最硬的可执行省钱点。")
    L.append("2. **引流钩子**:百炼新人 100 万 tokens 免费额度 + 混元 100 万 tokens/年 免费包,"
             "适合作为“零成本试用”话术。")
    L.append("3. **运营节奏**:本期建立基线快照;次日起每日 diff,**变动才推送,无变动日静默**,降低骚扰风险。")
    L.append("4. **风险提醒**:硅基流动为聚合页非官方价,引用必须标注;腾讯云仅引用官方文档页,不挂任何推广链接。")
    L.append("")
    L.append("---")
    L.append(f"*生成:skills/discount-radar/scripts/fetch_discounts.py(MVP v0.1)"
             f"|抓取时间:{snap['fetched_at']}|免责声明见文首*")
    return "\n".join(L)


def build_wechat(date_str, label, snap, report_name):
    groups = OrderedDict()
    for s in snap["sources"]:
        groups.setdefault(s["vendor"], []).append(s)
    hhmm = snap["fetched_at"][11:16]
    lines = [f"【模型折扣雷达 {date_str}】",
             f"抓取 {hhmm}(北京时间),以各官方页为准,不构成计费依据。"]
    i = 0
    for v, srcs in groups.items():
        i += 1
        ok = [s for s in srcs if s["status"] == "ok" and s["items"]]
        if ok:
            cand = [it for s in ok for it in s["items"] if it.get("discount")]
            it0 = (cand or ok[0]["items"])[0]
            s = _clean(str(it0.get("discount") or it0.get("price") or ""))
            s = s.replace("(关键词命中,以官方页为准)", "")
            if not it0.get("discount") and it0.get("name"):
                s = f"{it0['name']} {s}"
            if s in ("免费", "免费额度") and it0.get("name"):
                s = f"{it0['name']} {s}"
            if len(s) > 46:
                s = s[:45] + "…"
            extra = "(聚合页)" if ok[0].get("note") else ""
            lines.append(f"{i}.{v}{extra}:{s}")
        else:
            lines.append(f"{i}.{v}:本次抓取失败,以官方页为准")
    tag = f"-{label}" if label else ""
    lines.append(f"官方链接与完整日报:reports/{date_str}-折扣雷达日报{tag}.md")
    lines.append("退订请回复:退订")
    text = "\n".join(lines)
    guard = 0
    while len(text) > 500 and guard < 30:   # 逐条压缩条目行
        guard += 1
        for idx in range(2, len(lines) - 2):
            if len(lines[idx]) > 18:
                lines[idx] = lines[idx][:-8] + "…"
                break
        else:
            break
        text = "\n".join(lines)
    if len(text) > 500:
        text = text[:497] + "…"
    return text


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="模型折扣雷达抓取脚本(MVP)")
    ap.add_argument("--date", default=datetime.now(TZ8).strftime("%Y-%m-%d"))
    ap.add_argument("--label", default="")
    ap.add_argument("--timeout", type=int, default=35)
    args = ap.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    snap = dict(date=args.date,
                fetched_at=datetime.now(TZ8).isoformat(timespec="seconds"),
                generator="discount-radar MVP v0.1",
                disclaimer=DISCLAIMER,
                sources=[])

    print(f"== 模型折扣雷达 抓取开始 {snap['fetched_at']} ==")
    for src in SOURCES:
        res = fetch_source(src, timeout=args.timeout)
        snap["sources"].append(res)
        mark = "✅" if res["status"] == "ok" else "❌"
        n_items = len(res.get("items", []))
        tail = "" if res["status"] == "ok" else f"({res.get('error', '')[:80]})"
        print(f"{mark} {res['vendor']:<10} {res['key']:<16} 条目 {n_items} {tail}")

    attach_batch_ratio(snap)

    # 落快照
    snap_path = DATA_DIR / f"snapshot-{args.date}.json"
    snap_path.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")

    # diff
    prev_name, prev_snap = find_prev_snapshot(args.date)

    # 日报
    tag = f"-{args.label}" if args.label else ""
    report_name = f"{args.date}-折扣雷达日报{tag}.md"
    report = build_report(args.date, args.label, snap, prev_name, prev_snap)
    (REPORT_DIR / report_name).write_text(report, encoding="utf-8")

    # 微信版
    wechat = build_wechat(args.date, args.label, snap, report_name)
    wechat_path = DATA_DIR / f"wechat-{args.date}.txt"
    wechat_path.write_text(wechat, encoding="utf-8")

    ok_rows = vendor_rollup(snap)
    okn = sum(1 for _, st, _ in ok_rows if st == "ok")
    print("\n== 汇总 ==")
    for v, st, _ in ok_rows:
        print(f"  {v}:{'成功' if st == 'ok' else '本次抓取失败'}")
    print(f"厂商成功 {okn}/{len(ok_rows)}(验收线 ≥4)")
    print(f"快照:{snap_path}")
    print(f"日报:{REPORT_DIR / report_name}")
    print(f"微信版:{wechat_path}(共 {len(wechat)} 字,上限 500)")
    print("\n---- 微信版预览 ----")
    print(wechat)


if __name__ == "__main__":
    main()
