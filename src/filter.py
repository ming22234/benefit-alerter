from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Set
from src.config_loader import calculate_age
from src.models import BenefitItem, ClassifiedBenefits


def parse_iso_date(date_str: Optional[str]) -> Optional[date]:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def matches_region(item_region: str, sido: str, sigungu: str, include_nationwide: bool) -> bool:
    norm = item_region.strip()
    if not norm or norm == "전국":
        return include_nationwide

    # 시/군/구 토큰 분리 (예: "수원시 영통구" -> ["수원시", "수원", "영통구", "영통"])
    sigungu_tokens = []
    for part in sigungu.split():
        part = part.strip()
        if not part:
            continue
        sigungu_tokens.append(part)
        if len(part) >= 3 and part[-1] in ("시", "군", "구"):
            sigungu_tokens.append(part[:-1])

    # 공고 지역에 내 시/군/구(예: 수원, 영통구)가 직접 포함되어 있으면 매칭
    if sigungu_tokens and any(tok in norm for tok in sigungu_tokens):
        return True

    # 공고 지역이 광역 지자체 전체(예: "경기", "경기도")인 경우 매칭
    if sido and norm in (sido, f"{sido}시", f"{sido}특별시", f"{sido}광역시", f"{sido}도", f"{sido}특별자치도"):
        return True

    # 시/군/구 설정이 비어있고 시/도만 설정된 경우
    if sido and not sigungu and sido in norm:
        return True

    return False


def matches_age(user_age: int, min_age: Optional[int], max_age: Optional[int], include_unrestricted: bool) -> bool:
    if min_age is None and max_age is None:
        return include_unrestricted
    if min_age is not None and user_age < min_age:
        return False
    if max_age is not None and user_age > max_age:
        return False
    return True


def filter_and_classify_benefits(
    items: Iterable[BenefitItem],
    config: Dict[str, Any],
    seen_ids: Set[str],
    today: Optional[date] = None,
) -> ClassifiedBenefits:
    ref_today = today or date.today()
    profile = config.get("profile", {})
    interests = config.get("interests", {})
    notif = config.get("notification", {})

    user_age = calculate_age(profile.get("birth_year", 1995), ref_today)
    sido = profile.get("region_sido", "").strip()
    sigungu = profile.get("region_sigungu", "").strip()
    include_nationwide = profile.get("include_nationwide", True)
    include_age_unrestricted = profile.get("include_age_unrestricted", True)

    priority_keywords: List[str] = interests.get("priority_keywords", [])
    exclude_keywords: List[str] = interests.get("exclude_keywords", [])
    closing_soon_days: int = int(notif.get("closing_soon_days", 3))

    classified = ClassifiedBenefits()

    for item in items:
        combined_text = f"{item.title} {item.summary} {item.organization}"

        if any(ex_kw in combined_text for ex_kw in exclude_keywords):
            continue

        if not matches_region(item.region, sido, sigungu, include_nationwide):
            continue

        if not matches_age(user_age, item.min_age, item.max_age, include_age_unrestricted):
            continue

        item.is_priority = any(pk in combined_text for pk in priority_keywords)

        start_dt = parse_iso_date(item.start_date)
        end_dt = parse_iso_date(item.end_date)

        # 이미 마감된 공고 제외
        if end_dt and end_dt < ref_today:
            next_month = 1 if ref_today.month == 12 else ref_today.month + 1
            if ref_today.month in item.expected_months or next_month in item.expected_months:
                classified.upcoming_monthly.append(item)
            continue

        if end_dt:
            item.d_day = (end_dt - ref_today).days

        # 아직 시작 전이지만 14일 내 오픈하는 공고
        if start_dt and start_dt > ref_today:
            days_until_start = (start_dt - ref_today).days
            if days_until_start <= 14:
                classified.upcoming_monthly.append(item)
            continue

        # 정확한 시작/종료일 없이 연간 예상 오픈월만 있는 정기 사업
        if not start_dt and not end_dt and not item.is_always_open and item.expected_months:
            next_month = 1 if ref_today.month == 12 else ref_today.month + 1
            if ref_today.month in item.expected_months or next_month in item.expected_months:
                classified.upcoming_monthly.append(item)
            continue

        # 현재 신청 가능한 혜택 분류
        is_new = (item.id not in seen_ids) or (start_dt == ref_today)
        if is_new:
            classified.newly_opened.append(item)
        elif item.d_day is not None and 0 <= item.d_day <= closing_soon_days:
            classified.closing_soon.append(item)
        else:
            classified.currently_open.append(item)

    classified.newly_opened.sort(key=lambda x: (not x.is_priority, x.d_day if x.d_day is not None else 999))
    classified.closing_soon.sort(key=lambda x: (x.d_day if x.d_day is not None else 999, not x.is_priority))
    classified.currently_open.sort(key=lambda x: (not x.is_priority, x.d_day if x.d_day is not None else 999))

    return classified
