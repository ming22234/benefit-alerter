from datetime import date, datetime
import re
from typing import Any, Dict, Iterable, List, Optional, Set
from src.config_loader import calculate_age
from src.models import BenefitItem, ClassifiedBenefits

GENERIC_STOPWORDS = {
    "신청", "모집", "접수", "지원", "지원금", "청년", "사업", "안내", "공고",
    "시작", "마감", "오픈", "개설", "최대", "만원", "올해", "내달", "하반기",
    "상반기", "기간", "운영", "대상", "신규", "추가", "참여자", "교육생", "관심",
    "계좌", "적금", "바우처", "이용권", "장학금",
}

PROGRAM_NAME_REGEX = re.compile(
    r"([가-힣A-Za-z0-9]{2,10}(?:미래적금|도약계좌|내일저축계좌|내일저축|교육이용권|교육바우처|내일배움카드|누리카드|기회사다리금융|경기패스))"
)


def _extract_signature_tokens(title: str) -> Set[str]:
    compact = re.sub(r"\s+", "", title)
    prog_matches = set(PROGRAM_NAME_REGEX.findall(compact))

    words = re.findall(r"[가-힣A-Za-z0-9]{2,}", title)
    tokens = {w for w in words if w not in GENERIC_STOPWORDS and not w.isdigit()}
    return prog_matches | tokens


def deduplicate_similar_items(items: Iterable[BenefitItem]) -> List[BenefitItem]:
    """동일한 정책/적금/바우처(예: 청년미래적금 기사 여러 개)가 중복 수집될 때 대표 1건만 남긴다."""
    unique_items: List[BenefitItem] = []
    seen_programs: Set[str] = set()
    seen_token_sets: List[Set[str]] = []

    for item in items:
        compact = re.sub(r"\s+", "", item.title)
        programs = set(PROGRAM_NAME_REGEX.findall(compact))

        # 1) 핵심 고유 사업명(예: 청년미래적금, 청년도약계좌 등)이 이미 등장했으면 중복 제거
        if programs and (programs & seen_programs):
            continue

        # 2) 제목 핵심 키워드가 2개 이상 겹치면서 짧은 제목 기준 50% 이상 일치하면 중복 기사로 판단
        sig_tokens = _extract_signature_tokens(item.title)
        is_dup = False
        if sig_tokens:
            for prev_tokens in seen_token_sets:
                overlap = len(sig_tokens & prev_tokens)
                min_len = min(len(sig_tokens), len(prev_tokens))
                if overlap >= 2 and (overlap / max(min_len, 1)) >= 0.5:
                    is_dup = True
                    break
        if is_dup:
            continue

        unique_items.append(item)
        seen_programs.update(programs)
        if sig_tokens:
            seen_token_sets.append(sig_tokens)

    return unique_items


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

    sigungu_tokens = []
    for part in sigungu.split():
        part = part.strip()
        if not part:
            continue
        sigungu_tokens.append(part)
        if len(part) >= 3 and part[-1] in ("시", "군", "구"):
            sigungu_tokens.append(part[:-1])

    if sigungu_tokens and any(tok in norm for tok in sigungu_tokens):
        return True

    if sido and norm in (sido, f"{sido}시", f"{sido}특별시", f"{sido}광역시", f"{sido}도", f"{sido}특별자치도"):
        return True

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

    # 유사/중복 공고 및 뉴스 기사 1차 통합 제거
    deduped_items = deduplicate_similar_items(items)

    for item in deduped_items:
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

        # 이미 발송 이력(seen_ids)에 있는 공고는 절대 '신규'로 중복 발송하지 않음
        is_new = item.id not in seen_ids
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
