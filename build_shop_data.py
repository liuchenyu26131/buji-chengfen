#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清洗商城商品对照表，保留规格、价格、状态和全部 SKU。

数据流：
  产品使用卡_商城商品对照表.md
    -> 商城产品购买链接_标准版.csv（一 SKU 一行，人工可维护）
    -> 上线站点/data/shop.json（网页运行时数据）
"""

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE_MD = ROOT / "产品使用卡_商城商品对照表.md"
PRODUCT_MAIN = ROOT / "产品主表.csv"
STANDARD_CSV = ROOT / "商城产品购买链接_标准版.csv"
SHOP_JSON = HERE / "data" / "shop.json"
SECTION = "## 对照表（按产品编号）"
FIELDS = [
    "产品ID",
    "产品名称",
    "卡内规格",
    "商城商品名",
    "商城规格",
    "单价",
    "购买链接",
    "状态",
    "依据",
    "是否主链接",
]


def split_br(value):
    parts = re.split(r"<br\s*/?>", value or "", flags=re.IGNORECASE)
    return [part.strip() for part in parts if part.strip() and part.strip() not in {"—", "-"}]


def parse_status(value):
    text = re.sub(r"\*+", "", value or "").strip()
    if "｜" in text:
        status, evidence = text.split("｜", 1)
    elif "：" in text:
        status, evidence = text.split("：", 1)
    elif ":" in text:
        status, evidence = text.split(":", 1)
    else:
        status, evidence = text, ""
    return status.strip() or "未标注", evidence.strip()


def parse_sku(value):
    text = (value or "").strip()
    match = re.match(r"^(.*?)\s*·\s*¥\s*([0-9]+(?:\.[0-9]+)?)\s*$", text)
    if match:
        return match.group(1).strip(), match.group(2)
    return text, ""


def product_ids_from_main():
    with PRODUCT_MAIN.open(encoding="utf-8-sig", newline="") as handle:
        return {row["产品ID"].strip() for row in csv.DictReader(handle)}


def parse_markdown(path):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == SECTION)
    except StopIteration:
        raise SystemExit(f"找不到章节：{SECTION}")
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )

    rows = []
    seen = set()
    for line_no in range(start, end):
        line = lines[line_no]
        if not re.match(r"^\|\s*P\d{3}\s*\|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 7:
            raise SystemExit(f"第 {line_no + 1} 行列数不是 7：{len(cells)}")
        product_id, name, card_spec, mall_name, sku_raw, links_raw, status_raw = cells
        if product_id in seen:
            raise SystemExit(f"产品ID重复：{product_id}")
        seen.add(product_id)

        sku_lines = split_br(sku_raw)
        urls = re.findall(r"https?://[^\s)<]+", links_raw)
        status_lines = split_br(status_raw)
        count = max(1, len(sku_lines), len(urls))
        primary_marked = False

        for index in range(count):
            spec, price = parse_sku(sku_lines[index]) if index < len(sku_lines) else ("", "")
            url = urls[index] if index < len(urls) else ""
            status_text = status_lines[index] if index < len(status_lines) else (status_lines[0] if status_lines else "未标注")
            status, evidence = parse_status(status_text)
            if url and not re.match(r"^https?://", url):
                raise SystemExit(f"{product_id} 购买链接格式错误：{url}")
            is_primary = bool(url) and not primary_marked
            if is_primary:
                primary_marked = True
            rows.append({
                "产品ID": product_id,
                "产品名称": name,
                "卡内规格": card_spec,
                "商城商品名": mall_name,
                "商城规格": spec,
                "单价": price,
                "购买链接": url,
                "状态": status,
                "依据": evidence,
                "是否主链接": "是" if is_primary else "否",
            })

    snapshot_match = re.search(r"抓取于\s*(\d{4}-\d{2}-\d{2})", text)
    snapshot = snapshot_match.group(1) if snapshot_match else ""
    return rows, snapshot


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FIELDS:
            raise SystemExit(f"标准 CSV 表头必须为：{','.join(FIELDS)}")
        rows = []
        for row in reader:
            item = {field: (row.get(field) or "").strip() for field in FIELDS}
            if not re.fullmatch(r"P\d{3}", item["产品ID"]):
                raise SystemExit(f"产品ID格式错误：{item['产品ID']}")
            if not item["产品名称"]:
                raise SystemExit(f"{item['产品ID']} 缺少产品名称")
            if item["购买链接"] and not re.match(r"^https?://", item["购买链接"]):
                raise SystemExit(f"{item['产品ID']} 购买链接格式错误：{item['购买链接']}")
            if item["是否主链接"] not in {"是", "否"}:
                raise SystemExit(f"{item['产品ID']} 是否主链接必须为是/否")
            rows.append(item)
    return rows


def write_csv(rows):
    with STANDARD_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def validate(rows):
    expected = product_ids_from_main()
    actual = {row["产品ID"] for row in rows}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise SystemExit(f"产品ID不完整：缺少={missing}，多出={extra}")
    primary = {}
    for row in rows:
        if row["是否主链接"] == "是":
            if row["产品ID"] in primary:
                raise SystemExit(f"{row['产品ID']} 存在多个主链接")
            primary[row["产品ID"]] = row
    return primary


def build_json(rows, primary, snapshot):
    products = {}
    for row in rows:
        product_id = row["产品ID"]
        if product_id not in products:
            p = primary.get(product_id)
            products[product_id] = {
                "id": product_id,
                "name": row["产品名称"],
                "cardSpec": row["卡内规格"],
                "mallName": row["商城商品名"],
                "url": p["购买链接"] if p else "",
                "status": p["状态"] if p else "未上架",
                "primary": None,
                "skus": [],
            }
        sku = {
            "spec": row["商城规格"],
            "price": float(row["单价"]) if row["单价"] else None,
            "url": row["购买链接"],
            "status": row["状态"],
            "evidence": row["依据"],
        }
        products[product_id]["skus"].append(sku)
        if row["是否主链接"] == "是":
            products[product_id]["primary"] = sku

    payload = {
        "builtAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "priceSnapshot": snapshot,
        "source": STANDARD_CSV.name,
        "products": products,
    }
    SHOP_JSON.parent.mkdir(parents=True, exist_ok=True)
    SHOP_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-md", action="store_true", help="从 MD 重建标准 CSV")
    args = parser.parse_args()

    snapshot = ""
    if args.from_md or not STANDARD_CSV.exists():
        rows, snapshot = parse_markdown(SOURCE_MD)
        write_csv(rows)
    else:
        rows = read_csv(STANDARD_CSV)
        text = SOURCE_MD.read_text(encoding="utf-8")
        match = re.search(r"抓取于\s*(\d{4}-\d{2}-\d{2})", text)
        snapshot = match.group(1) if match else ""

    primary = validate(rows)
    build_json(rows, primary, snapshot)
    linked = len(primary)
    print(f"商城数据已生成：{len(primary)} 个产品有主链接，{len(rows)} 条 SKU 记录")
    print(f"标准表：{STANDARD_CSV}")
    print(f"站点数据：{SHOP_JSON}")


if __name__ == "__main__":
    main()
