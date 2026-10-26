import json
from pathlib import Path
from typing import Set
from src.collectors.gov24_api import collect_gov24_benefits
from src.collectors.seed_collector import collect_seed_benefits
from src.collectors.web_scrapers import (
    scrape_policy_news_rss,
    scrape_wevity_scholarships_and_support,
)
from src.config_loader import load_config
from src.filter import filter_and_classify_benefits
from src.notifier import format_daily_briefing, send_telegram_message

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.yaml"
SEED_PATH = BASE_DIR / "data" / "annual_calendar.json"
SEEN_PATH = BASE_DIR / "data" / "seen_history.json"
PREVIEW_PATH = BASE_DIR / "data" / "latest_preview.md"


def load_seen_ids(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("seen_ids", []))
    except Exception:
        return set()


def save_seen_ids(path: Path, seen_ids: Set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"seen_ids": sorted(seen_ids)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    config = load_config(CONFIG_PATH)
    sido = config.get("profile", {}).get("region_sido", "")
    sigungu = config.get("profile", {}).get("region_sigungu", "")

    seed_items = collect_seed_benefits(SEED_PATH)
    gov24_items = collect_gov24_benefits(sido=sido)
    web_items = scrape_wevity_scholarships_and_support()
    news_items = scrape_policy_news_rss(sido=sido, sigungu=sigungu)

    all_items = seed_items + gov24_items + web_items + news_items
    seen_ids = load_seen_ids(SEEN_PATH)

    classified = filter_and_classify_benefits(
        items=all_items,
        config=config,
        seen_ids=seen_ids,
    )

    briefing_text = format_daily_briefing(classified, config)
    sent = send_telegram_message(briefing_text, preview_path=PREVIEW_PATH)

    for item in classified.newly_opened:
        seen_ids.add(item.id)
    for item in classified.currently_open:
        seen_ids.add(item.id)
    save_seen_ids(SEEN_PATH, seen_ids)

    print(
        f"[DONE] 수집 총 {len(all_items)}건 | 신규 {len(classified.newly_opened)}건 | "
        f"마감임박 {len(classified.closing_soon)}건 | 상시/진행중 {len(classified.currently_open)}건 | "
        f"텔레그램 발송={sent} | 프리뷰={PREVIEW_PATH}"
    )


if __name__ == "__main__":
    main()
