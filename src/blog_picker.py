from datetime import date
import json
from pathlib import Path
import sys
from typing import Dict, List, Set
from src.collectors.gov24_api import collect_gov24_benefits
from src.collectors.seed_collector import collect_seed_benefits
from src.collectors.web_scrapers import (
    scrape_lllcard_live_periods,
    scrape_wevity_scholarships_and_support,
)
from src.models import BenefitItem

BASE_DIR = Path(__file__).resolve().parent.parent
SEED_PATH = BASE_DIR / "data" / "annual_calendar.json"
BLOG_HISTORY_PATH = BASE_DIR / "data" / "blog_history.json"


def load_blog_history(path: Path = BLOG_HISTORY_PATH) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("posted_benefits", [])
    except Exception:
        return []


def save_blog_history(benefit_id: str, title: str, file_path: str, path: Path = BLOG_HISTORY_PATH) -> None:
    history = load_blog_history(path)
    history.append(
        {
            "date": date.today().strftime("%Y-%m-%d"),
            "id": benefit_id,
            "title": title,
            "file": file_path,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"posted_benefits": history}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def generalize_region_for_blog(region: str) -> str:
    """개인 거주지(예: 수원시 영통구)가 특정되지 않도록 전국 또는 광역(경기도·수도권) 단위로 일반화"""
    norm = region.strip()
    if not norm or norm == "전국":
        return "전국 공통"
    if "경기" in norm or "수원" in norm:
        return "경기도 (31개 시·군)"
    if "서울" in norm:
        return "서울특별시"
    return norm


def pick_candidates(top_n: int = 5) -> List[Dict[str, str]]:
    posted = load_blog_history()
    posted_ids: Set[str] = {row.get("id", "") for row in posted}

    items: List[BenefitItem] = (
        scrape_lllcard_live_periods()
        + collect_seed_benefits(SEED_PATH)
        + collect_gov24_benefits()
        + scrape_wevity_scholarships_and_support()
    )

    today = date.today()
    candidates: List[Dict[str, str]] = []

    for item in items:
        if item.id in posted_ids:
            continue
        # 이미 마감일이 지난 공고는 제외
        if item.end_date and item.end_date < today.strftime("%Y-%m-%d"):
            continue
        # 전국 공통 또는 경기도/서울 광역 혜택만 블로그 후보로 선정 (타 지방 단독 공고 제외)
        if item.region not in ("전국", "경기", "경기 수원시", "서울"):
            continue

        is_narrow_local = ("수원시" in item.title) and ("경기" not in item.title)
        priority_score = 0
        if item.region == "전국":
            priority_score += 25  # 전국 공통 혜택 최우선
        elif "경기" in item.region:
            priority_score += 20  # 경기도 전체 혜택 차순위
        if item.end_date:
            priority_score += 15  # 마감일이 명확한 시즌성 혜택 가산점
        if is_narrow_local:
            priority_score -= 30

        candidates.append(
            {
                "id": item.id,
                "title": item.title,
                "category": item.category,
                "organization": item.organization,
                "blog_region": generalize_region_for_blog(item.region),
                "target_summary": item.target_summary.replace("수원시 등 ", ""),
                "summary": item.summary.replace("수원페이 등 ", ""),
                "apply_period_text": item.apply_period_text.replace("수원시 ", ""),
                "url": item.url,
                "apply_url": item.apply_url,
                "score": priority_score,
            }
        )

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:top_n]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) >= 4 and sys.argv[1] == "record":
        save_blog_history(sys.argv[2], sys.argv[3], sys.argv[4])
        print(f"[OK] 블로그 작성 이력 저장 완료: {sys.argv[2]} - {sys.argv[3]}")
    else:
        top = pick_candidates(5)
        print(json.dumps(top, ensure_ascii=False, indent=2))
