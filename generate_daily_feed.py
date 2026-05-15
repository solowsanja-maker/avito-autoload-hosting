#!/usr/bin/env python3
import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

SOURCE_CSV = Path("data/shuffled_source.csv")
STATE_PATH = Path("data/state.json")
OUT_FEED = Path("public/feed.xml")
OUT_REPORT = Path("public/batch_report.json")
PHOTOS_ROOT = Path("photos")

CITY_PRIORITY = {
    "Саратов": 0,
    "Энгельс": 1,
    "Маркс": 2,
}

PRODUCT_DEFAULT = {
    "Category": "Ремонт и строительство",
    "GoodsType": "Окна и балконы",
    "AdType": "Товар приобретен на продажу",
    "Condition": "Новое",
}

SERVICE_DEFAULT = {
    "Category": "Предложение услуг",
    "ServiceType": "Ремонт и отделка",
    "ServiceSubtype": "Окна и балконы",
    "Specialty": "Остекление и ремонт балконов",
    "WorkExperience": "5 лет",
    "TeamSize": "2-4 человека",
    "WorkTimeFrom": "09:00",
    "WorkTimeTo": "21:00",
    "Guarantee": "Есть",
    "MaterialPurchase": "Возможна",
}


def clean(text: str) -> str:
    return (text or "").strip()


def detect_city(address: str) -> str:
    a = (address or "").lower()
    if "энгельс" in a:
        return "Энгельс"
    if "маркс" in a:
        return "Маркс"
    return "Саратов"


def detect_bucket(source_file: str) -> str:
    s = (source_file or "").lower()
    s_norm = s.replace("-", "_").replace(" ", "_")
    for b in (
        "вертикальные_шторы",
        "москитные_сетки",
        "мягкие_окна_беседки",
        "остекление_балконов",
        "пластиковые_окна",
        "рулонные_шторы",
    ):
        if b in s_norm:
            return b
    return "прочее"


def add_text(parent: ET.Element, tag: str, value: str) -> None:
    elem = ET.SubElement(parent, tag)
    elem.text = clean(value)


def add_category_specific_fields(ad: ET.Element, bucket: str) -> None:
    if bucket == "остекление_балконов":
        for tag, value in SERVICE_DEFAULT.items():
            add_text(ad, tag, value)
        return

    for tag, value in PRODUCT_DEFAULT.items():
        add_text(ad, tag, value)

    if bucket in {"вертикальные_шторы", "рулонные_шторы", "прочее"}:
        add_text(ad, "GoodsSubType", "Москитные сетки и фурнитура для окон")
        add_text(ad, "ProductType", "Рулонные шторы и жалюзи")
    elif bucket == "москитные_сетки":
        add_text(ad, "GoodsSubType", "Москитные сетки и фурнитура для окон")
        add_text(ad, "ProductType", "Москитные сетки")
        add_text(ad, "ProductSubType", "Готовая москитная сетка")
        add_text(ad, "PurposeFor", "Окон")
        add_text(ad, "MeshType", "Антимоскитная")
        add_text(ad, "MeshShape", "Рамная")
    elif bucket == "мягкие_окна_беседки":
        add_text(ad, "GoodsSubType", "Мягкие окна")
        add_text(ad, "PackagingType", "Окно на заказ")
        add_text(ad, "MinSaleQuantity", "1")
        add_text(ad, "PriceFor", "Окно")
        add_text(ad, "Material", "ПВХ")
        add_text(ad, "Thickness", "0,7 мм")
        add_text(ad, "Width", "1000")
        add_text(ad, "Height", "1000")
        add_text(ad, "Length", "1000")
    elif bucket == "пластиковые_окна":
        add_text(ad, "GoodsSubType", "Окна")
        add_text(ad, "MaterialType", "Пластик")
        add_text(ad, "ProfileBrand", "Rehau")
        add_text(ad, "BusinessSubType", "Поворотно-откидное")


def normalize_text_geo(text: str, city: str) -> str:
    t = text or ""
    t = re.sub(r"\bВоронежская\s+обл\.?\b", "Саратовская обл.", t, flags=re.IGNORECASE)
    t = re.sub(r"\bВоронеж\b", city, t, flags=re.IGNORECASE)
    t = re.sub(r"\bВоронеже\b", city, t, flags=re.IGNORECASE)
    t = re.sub(r"\bВоронежа\b", city, t, flags=re.IGNORECASE)
    return t


def load_rows() -> list[dict]:
    with SOURCE_CSV.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    prepared = []
    for row in rows:
        title = (row.get("title") or "").lower()
        row["_city"] = detect_city(row.get("address", ""))
        row["_bucket"] = detect_bucket(row.get("source_file", ""))
        if row["_bucket"] == "прочее":
            if "мягк" in title and "окн" in title:
                row["_bucket"] = "мягкие_окна_беседки"
            elif "москит" in title:
                row["_bucket"] = "москитные_сетки"
            elif "остеклен" in title and "балкон" in title:
                row["_bucket"] = "остекление_балконов"
            elif "пластиков" in title and "окн" in title:
                row["_bucket"] = "пластиковые_окна"
            elif "вертикальн" in title:
                row["_bucket"] = "вертикальные_шторы"
            elif "рулонн" in title or "жалюз" in title:
                row["_bucket"] = "рулонные_шторы"
        row["_id"] = row.get("external_id") or row.get("source_id") or ""
        row["description"] = normalize_text_geo(row.get("description", ""), row["_city"])
        row["address"] = normalize_text_geo(row.get("address", ""), row["_city"])
        prepared.append(row)

    # Don't sort - keep the shuffled order from CSV
    return prepared


def load_state(reset: bool) -> dict:
    if reset or not STATE_PATH.exists():
        return {"next_index": 0, "history": []}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def build_photo_index(base_url: str) -> dict[str, list[str]]:
    photos = {}
    for cat_dir in PHOTOS_ROOT.iterdir():
        if not cat_dir.is_dir():
            continue
        urls = []
        for file_path in sorted(cat_dir.iterdir()):
            if file_path.is_file():
                rel = file_path.as_posix()
                urls.append(f"{base_url}/{rel}")
        photos[cat_dir.name] = urls
    return photos


def build_feed(batch: list[dict], photo_urls: dict[str, list[str]]) -> None:
    root = ET.Element("Ads", {"formatVersion": "3", "target": "Avito.ru"})
    photo_counters = {k: 0 for k in photo_urls}

    for row in batch:
        ad = ET.SubElement(root, "Ad")
        add_text(ad, "Id", row.get("_id", ""))
        add_text(ad, "Title", row.get("title", ""))
        add_text(ad, "Description", row.get("description", ""))
        add_text(ad, "Address", row.get("address", ""))

        price = "".join(ch for ch in clean(row.get("price", "0")) if ch.isdigit()) or "0"
        add_text(ad, "Price", price)

        bucket = row.get("_bucket", "прочее")
        add_category_specific_fields(ad, bucket)

        images = ET.SubElement(ad, "Images")
        urls = photo_urls.get(bucket, [])
        if urls:
            idx = photo_counters[bucket]
            ET.SubElement(images, "Image", {"url": urls[idx % len(urls)]})
            ET.SubElement(images, "Image", {"url": urls[(idx + 1) % len(urls)]})
            ET.SubElement(images, "Image", {"url": urls[(idx + 2) % len(urls)]})
            photo_counters[bucket] += 1

    OUT_FEED.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(OUT_FEED, encoding="utf-8", xml_declaration=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate daily Avito XML batch")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    rows = load_rows()
    state = load_state(args.reset)
    next_index = int(state.get("next_index", 0))

    if next_index >= len(rows):
        next_index = len(rows)

    end_index = min(next_index + args.batch_size, len(rows))
    batch = rows[next_index:end_index]
    active_rows = rows[:end_index] if end_index > 0 else rows

    photos = build_photo_index(args.base_url.rstrip("/"))
    build_feed(active_rows, photos)

    city_stats = {"Саратов": 0, "Энгельс": 0, "Маркс": 0}
    for r in batch:
        city_stats[r["_city"]] = city_stats.get(r["_city"], 0) + 1

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "batch_from": next_index,
        "batch_to": end_index,
        "batch_size": len(batch),
        "active_in_feed": len(active_rows),
        "city_stats": city_stats,
        "sample_ids": [r.get("_id", "") for r in batch[:10]],
    }
    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    state["next_index"] = end_index
    state.setdefault("history", []).append(report)
    save_state(state)

    print("total_rows", len(rows))
    print("batch_from", next_index)
    print("batch_to", end_index)
    print("batch_size_real", len(batch))
    print("city_stats", city_stats)


if __name__ == "__main__":
    main()
