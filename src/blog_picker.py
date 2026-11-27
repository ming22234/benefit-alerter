from datetime import date
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Set
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

# 동일 제도·주제 재발송 금지 쿨다운(일): 최소 120일 이내에는 같은 ID나 같은 핵심 제도명을 절대 다시 뽑지 않는다.
REPOST_COOLDOWN_DAYS = 120

BLOG_NOISE_KEYWORDS = (
    "국회의원",
    "명예보좌관",
    "보좌관",
    "서포터즈",
    "기자단",
    "홍보대사",
    "공모전",
    "아이디어",
    "해커톤",
    "자원봉사",
    "봉사단",
    "멘토단",
    "체험단",
    "모니터링단",
    "슬로건",
    "영상공모",
    "수기공모",
    "농업인",
    "어업인",
    "임업인",
    "참전유공자",
    "경로당",
)


def normalize_benefit_key(title: str) -> str:
    """'[경기] 2026 평생교육이용권 신청 접수 (우수이용자)' -> '평생교육이용권' 식으로 핵심 제도명을 추출해 중복 비교"""
    s = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", title or "")
    s = re.sub(r"\b20\d{2}년?\b", " ", s)
    stop_words = (
        "신청", "접수", "모집", "안내", "방법", "자격", "조건", "조회", "지원사업",
        "지원", "사업", "혜택", "정리", "신규", "추가", "상반기", "하반기", "1차", "2차",
        "경기도", "경기", "서울특별시", "서울", "수원시", "전국", "전국민",
    )
    for sw in stop_words:
        s = s.replace(sw, " ")
    s = re.sub(r"[^가-힣a-zA-Z0-9]", "", s).lower()
    return s[:18]


def load_blog_history(path: Path = BLOG_HISTORY_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("posted_benefits", [])
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def save_blog_history(
    benefit_id: str,
    title: str,
    file_path: str,
    *,
    format_id: str = "",
    theme_id: str = "",
    blog_category: str = "",
    ref_date: Optional[date] = None,
    path: Path = BLOG_HISTORY_PATH,
) -> None:
    history = load_blog_history(path)
    entry: Dict[str, Any] = {
        "date": (ref_date or date.today()).strftime("%Y-%m-%d"),
        "id": benefit_id,
        "title": title,
        "norm_key": normalize_benefit_key(title),
        "file": file_path,
    }
    if format_id:
        entry["format_id"] = format_id
    if theme_id:
        entry["theme_id"] = theme_id
    if blog_category:
        entry["blog_category"] = blog_category

    history.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"posted_benefits": history}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def generalize_region_for_blog(region: str) -> str:
    """개인 세부 거주지(예: 수원시 영통구)가 특정되지 않도록 전국 또는 광역 단위로 일반화"""
    norm = (region or "").strip()
    if not norm or norm == "전국":
        return "전국 공통"
    if "경기" in norm or "수원" in norm:
        return "경기도 (31개 시·군)"
    if "서울" in norm:
        return "서울특별시"
    return norm


def _recent_history_sets(
    history: List[Dict[str, Any]],
    today: date,
    cooldown_days: int = REPOST_COOLDOWN_DAYS,
) -> tuple[Set[str], Set[str]]:
    blocked_ids: Set[str] = set()
    blocked_keys: Set[str] = set()
    for row in history:
        dt_str = str(row.get("date") or "")
        within_cooldown = True
        if dt_str:
            try:
                past_dt = date.fromisoformat(dt_str[:10])
                within_cooldown = (today - past_dt).days < cooldown_days
            except ValueError:
                within_cooldown = True
        if not within_cooldown:
            continue
        bid = str(row.get("id") or "").strip()
        if bid:
            blocked_ids.add(bid)
        nk = str(row.get("norm_key") or normalize_benefit_key(str(row.get("title") or ""))).strip()
        if len(nk) >= 3:
            blocked_keys.add(nk)
    return blocked_ids, blocked_keys


def pick_candidates(
    top_n: int = 10,
    today: Optional[date] = None,
    history_path: Path = BLOG_HISTORY_PATH,
    items_override: Optional[List[BenefitItem]] = None,
) -> List[Dict[str, Any]]:
    ref_today = today or date.today()
    posted = load_blog_history(history_path)
    blocked_ids, blocked_keys = _recent_history_sets(posted, ref_today)

    # 직전 발행 카테고리와 다른 분야에 소폭 가산점을 주어 블로그 카테고리 편중 완화
    last_cat = str(posted[-1].get("blog_category") or "") if posted else ""

    items: List[BenefitItem] = (
        items_override
        if items_override is not None
        else (
            scrape_lllcard_live_periods()
            + collect_seed_benefits(SEED_PATH)
            + collect_gov24_benefits(sido="경기", today=ref_today)
            + scrape_wevity_scholarships_and_support()
        )
    )

    candidates: List[Dict[str, Any]] = []
    seen_batch_keys: Set[str] = set()

    for item in items:
        if item.id in blocked_ids:
            continue

        norm_key = normalize_benefit_key(item.title)
        if len(norm_key) >= 3 and (norm_key in blocked_keys or norm_key in seen_batch_keys):
            continue

        combined_txt = f"{item.title} {item.organization} {item.summary}"
        if any(bad in combined_txt for bad in BLOG_NOISE_KEYWORDS):
            continue

        # 마감일이 지난 공고 제외
        if item.end_date and item.end_date < ref_today.strftime("%Y-%m-%d"):
            continue

        # 전국 공통 또는 경기도/서울 광역 혜택만 블로그 후보로 선정
        if item.region not in ("전국", "경기", "경기 수원시", "서울"):
            continue

        # 현재 월(시즌) 적합도 및 우선순위 점수 계산
        is_narrow_local = ("수원시" in item.title) and ("경기" not in item.title)
        priority_score = 0
        if item.region == "전국":
            priority_score += 26
        elif "경기" in item.region:
            priority_score += 20

        if item.end_date:
            priority_score += 14
        if item.expected_months and ref_today.month in item.expected_months:
            priority_score += 8
        if item.id.startswith("seed_"):
            priority_score += 6  # 검증된 시드 공고 정보 품질 우대
        if is_narrow_local:
            priority_score -= 35

        # 날짜와 ID 조합의 결정적 미세 회전값(0~5점)으로 매일 다양한 분야가 자연스럽게 선택되도록 분산
        jitter = sum(ord(ch) for ch in f"{ref_today.isoformat()}:{item.id}") % 6
        priority_score += jitter

        if last_cat and last_cat in (item.category or ""):
            priority_score -= 4

        if len(norm_key) >= 3:
            seen_batch_keys.add(norm_key)

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
