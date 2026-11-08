#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把案例总库拆成“产品案例索引 + 单产品 JSON”。

映射规则：
  1. 案例自带 productIds 时，按产品编号精确关联。
  2. 旧案例没有 productIds 时，用 case_product_map.json 中的关键词匹配。

同一产品族下的多个规格共享关键词，但每个 P 编号仍生成独立文件。
"""

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "cases"
MAP_FILE = HERE / "case_product_map.json"
DEFAULT_SOURCE = Path(
    os.environ.get(
        "CASE_DATA_JSON",
        r"D:\Personal\Documents\GitHub\case-images\data.json",
    )
)


def natural_key(value):
    text = str(value or "")
    digits = "".join(ch for ch in text if ch.isdigit())
    return (int(digits) if digits else 10**12, text)


def source_commit(path):
    try:
        return subprocess.check_output(
            ["git", "-C", str(path.parent), "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def case_text(record):
    supplements = record.get("supplement") or []
    tags = record.get("tags") or []
    return " ".join(map(str, supplements)) + " " + " ".join(map(str, tags))


def compact_case(record):
    outcome = record.get("outcome") or {}
    images = record.get("file") or []
    if not isinstance(images, list):
        images = [images]
    return {
        "id": str(record.get("id") or ""),
        "type": str(record.get("type") or ""),
        "user": str(record.get("user") or "群友"),
        "problem": [str(x) for x in (record.get("problem") or [])],
        "supplement": [str(x) for x in (record.get("supplement") or [])],
        "status": str(outcome.get("status") or ""),
        "effect": str(outcome.get("description") or "").strip(),
        "summary": str(record.get("summary") or "").strip(),
        "images": [str(x) for x in images if str(x).startswith("https://")],
        "captions": [str(x) for x in (record.get("captions") or [])],
    }


def write_json(path, value, indent=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    separators = None if indent else (",", ":")
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=indent, separators=separators) + "\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()

    source = args.source.resolve()
    if not source.exists():
        raise SystemExit(f"案例总库不存在：{source}")

    records = json.loads(source.read_text(encoding="utf-8"))
    mapping = json.loads(MAP_FILE.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise SystemExit("案例总库必须是 JSON 数组")

    usable = [
        record for record in records
        if record.get("type") not in {"recipe", "trust"}
    ]
    products = {}
    family_counts = {}

    for family_id, family in (mapping.get("families") or {}).items():
        keywords = [str(x) for x in (family.get("keywords") or []) if str(x).strip()]
        family_products = [str(x) for x in (family.get("products") or []) if str(x).strip()]
        matched = []

        for record in usable:
            explicit = {str(x) for x in (record.get("productIds") or [])}
            keyword_hit = bool(keywords) and any(
                keyword in case_text(record) for keyword in keywords
            )
            if explicit.intersection(family_products) or keyword_hit:
                matched.append(record)

        by_id = {}
        for record in matched:
            case_id = str(record.get("id") or "")
            if case_id:
                by_id[case_id] = compact_case(record)
        items = sorted(by_id.values(), key=lambda item: natural_key(item["id"]))
        family_counts[family_id] = len(items)

        for product_id in family_products:
            if not items:
                continue
            payload = {
                "id": product_id,
                "familyId": family_id,
                "family": str(family.get("label") or family_id),
                "count": len(items),
                "items": items,
            }
            write_json(OUT / f"{product_id}.json", payload)
            products[product_id] = {
                "count": len(items),
                "file": f"{product_id}.json",
                "family": payload["family"],
            }

    manifest = {
        "builtAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sourceCommit": source_commit(source),
        "sourceRecords": len(records),
        "eligibleRecords": len(usable),
        "families": family_counts,
        "products": products,
        "disclaimer": "群友个案体验，不等同于疗效结论；请勿据此自行诊断或调整治疗。",
    }
    write_json(OUT / "index.json", manifest, indent=1)
    print(f"案例文件已生成：{len(products)} 个产品，来源 {source}")
    for product_id, meta in sorted(products.items()):
        print(f"  {product_id}: {meta['count']} 条 · {meta['family']}")


if __name__ == "__main__":
    main()
