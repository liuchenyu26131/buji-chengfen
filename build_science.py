#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_science.py — 把「功用科普md」里的科普稿编译成站点数据 data/science.json

真源（只读，不修改）：
  ../功用科普md/*.md      命名规律：{成分键}_[...]_{版本}.md

输出：
  data/science.json       成分级科普索引（多版本）+ 产品级整包映射

设计要点：
  - 键用「成分键」(如 029_烟酸B3)，与单品目录/映射表一致，不绑定产品/SKU
  - 每个成分下挂多个版本(versions)，正文转成 HTML 内联，供前端两版切换
  - products 段是「产品级整包」映射：产品ID -> {key, version}；复方产品可指向
    某个整包条目。当前烟酸试点只登记 P060/P061，其余产品留空由前端回退到成分级。
  - 本脚本由 build_site_json.py 在 build 末尾调用，也可单独运行

用法：
  python build_science.py
"""

import html
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "功用科普md"
DATA = HERE / "data"
OUT = DATA / "science.json"

# 版本识别：文件名里命中即归到该版本，越靠前优先级越高
VERSION_RULES = [
    ("plain", ["大白话", "通俗", "白话"]),
    ("orthomolecular", ["正分子与功能医学视角", "正分子观点", "正分子", "观点"]),
    ("professional", ["专业版", "循证", "专业"]),
]
VERSION_LABELS = {
    "plain": "大白话版",
    "orthomolecular": "正分子与功能医学视角",
    "professional": "专业版",
}

# 产品级整包映射（烟酸试点）。复方产品的整包科普到位后，在此按产品ID登记。
PRODUCT_PACKS = {
    "P060": {"key": "029_烟酸B3", "label": "烟酸（维生素B3）原料粉"},
    "P061": {"key": "029_烟酸B3", "label": "烟酸（维生素B3）代灌胶囊"},
}


def inline(s):
    """行内 markdown：加粗、行内代码，并转义 HTML。"""
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def is_table_sep(line):
    return bool(re.match(r"^\s*\|?[\s:\-|]+\|?\s*$", line)) and "-" in line


def split_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def md_to_html(md):
    """轻量 markdown -> HTML，覆盖本仓库科普稿用到的语法。"""
    lines = md.splitlines()
    out = []
    i = 0
    n = len(lines)

    while i < n:
        raw = lines[i]
        line = raw.rstrip()

        # 空行
        if not line.strip():
            i += 1
            continue

        # 分隔线
        if re.match(r"^\s*---+\s*$", line):
            out.append("<hr>")
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            lvl = len(m.group(1))
            txt = inline(m.group(2).strip())
            out.append(f"<h{lvl}>{txt}</h{lvl}>")
            i += 1
            continue

        # 引用块（连续 > 行合并）
        if line.lstrip().startswith(">"):
            block = []
            while i < n and lines[i].lstrip().startswith(">"):
                block.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            inner = md_to_html("\n".join(block))
            out.append(f"<blockquote>{inner}</blockquote>")
            continue

        # 表格（当前行是表头，下一行是分隔行）
        if "|" in line and i + 1 < n and is_table_sep(lines[i + 1]):
            head = split_row(line)
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(split_row(lines[i]))
                i += 1
            th = "".join(f"<th>{inline(c)}</th>" for c in head)
            body = []
            for r in rows:
                cells = "".join(f"<td>{inline(c)}</td>" for c in r)
                body.append(f"<tr>{cells}</tr>")
            out.append(
                "<div class='sc-table'><table><thead><tr>" + th +
                "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"
            )
            continue

        # 无序列表
        if re.match(r"^\s*-\s+", line):
            items = []
            while i < n and re.match(r"^\s*-\s+", lines[i]):
                items.append(re.sub(r"^\s*-\s+", "", lines[i]))
                i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            continue

        # 有序列表
        if re.match(r"^\s*\d+\.\s+", line):
            items = []
            while i < n and re.match(r"^\s*\d+\.\s+", lines[i]):
                items.append(re.sub(r"^\s*\d+\.\s+", "", lines[i]))
                i += 1
            out.append("<ol>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ol>")
            continue

        # 普通段落（连续非特殊行合并）
        para = [line.strip()]
        i += 1
        while i < n:
            nxt = lines[i].rstrip()
            if (not nxt.strip() or re.match(r"^\s*(#{1,6}\s|>|-\s|\d+\.\s|---+\s*$)", nxt)
                    or ("|" in nxt and i + 1 < n and is_table_sep(lines[i + 1]))):
                break
            para.append(nxt.strip())
            i += 1
        out.append("<p>" + inline(" ".join(para)) + "</p>")

    return "\n".join(out)


def detect_version(name):
    for ver, kws in VERSION_RULES:
        for kw in kws:
            if kw in name:
                return ver
    return None


def parse_key(name):
    """从文件名剥离尾部版本词，得到成分键（如 029_烟酸B3、20_K2-MK4）。

    旧实现用 ^(\\d+_[^-]+?)_ 取前缀，一旦成分名里带连字符（Ca-AKG、K2-MK4）
    就会截断成裸编号 17/20，导致 MK4 与 MK7 落到同一个键、互相覆盖。
    改为从右往左剥版本词：版本词可能叠加（_正分子与功能医学视角_大白话），
    循环剥离即可，且完全不依赖连字符。
    """
    s = name
    for _ in range(4):
        cut = False
        for _ver, kws in VERSION_RULES:
            for kw in kws:
                suffix = "_" + kw
                if s.endswith(suffix) and len(s) > len(suffix):
                    s = s[: -len(suffix)]
                    cut = True
                    break
            if cut:
                break
        if not cut:
            break
    return s


def title_of(md, fallback):
    m = re.search(r"^#\s+(.+)$", md, re.M)
    return m.group(1).strip() if m else fallback


def main():
    science = {"compositions": {}, "products": PRODUCT_PACKS, "versionLabels": VERSION_LABELS}
    if not SRC.exists():
        print("（未找到功用科普md 目录，跳过）")
        return

    for path in sorted(SRC.glob("*.md")):
        name = path.stem
        ver = detect_version(name)
        if not ver:
            print(f"  跳过（未识别版本）：{name}")
            continue
        key = parse_key(name)
        md = path.read_text(encoding="utf-8")
        comp = science["compositions"].setdefault(key, {"key": key, "versions": {}})
        comp["name"] = comp.get("name") or key
        comp["versions"][ver] = {
            "version": ver,
            "label": VERSION_LABELS[ver],
            "title": title_of(md, name),
            "source": name,
            "html": md_to_html(md),
        }
        print(f"  登记 {key} / {ver} <- {name}")

    DATA.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(science, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"✅ science.json 已生成（{OUT.stat().st_size/1024:.1f} KB）")


if __name__ == "__main__":
    main()
