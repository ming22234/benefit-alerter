from datetime import date
import os
import re
from typing import List, Optional, Tuple
import requests
from src.models import BenefitItem

GOV24_SERVICE_LIST_URL = "https://api.odcloud.kr/api/gov24/v3/serviceList"


def extract_dates_from_text(text: str) -> Tuple[Optional[str], Optional[str], bool]:
    if not text:
        return None, None, False
    if "상시" in text or "연중" in text:
        return None, None, True
    matches = re.findall(r"(202\d)[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})", text)
    if len(matches) >= 2:
        s_y, s_m, s_d = matches[0]
        e_y, e_m, e_d = matches[1]
        return (
            f"{int(s_y):04d}-{int(s_m):02d}-{int(s_d):02d}",
            f"{int(e_y):04d}-{int(e_m):02d}-{int(e_d):02d}",
            False,
        )
    if len(matches) == 1:
        e_y, e_m, e_d = matches[0]
        return None, f"{int(e_y):04d}-{int(e_m):02d}-{int(e_d):02d}", False
    return None, None, False


def collect_gov24_benefits(
    sido: str = "",
    max_pages: int = 3,
    today: Optional[date] = None,
) -> List[BenefitItem]:
    api_key = os.getenv("DATA_GO_KR_API_KEY", "").strip()
    if not api_key:
        return []

    ref_today = today or date.today()
    # 매일 다른 페이지 구간을 순환 탐색해 고정 1~2페이지만 반복 수집되는 현상 방지
    start_page = ((ref_today.toordinal() % 18) * max_pages) + 1
    pages = [1] + [start_page + i for i in range(max_pages) if (start_page + i) != 1]

    results: List[BenefitItem] = []
    seen_svc = set()
    for page in pages[: max_pages + 1]:
        params = {
            "serviceKey": api_key,
            "page": page,
            "perPage": 60,
            "returnType": "JSON",
        }
        try:
            resp = requests.get(GOV24_SERVICE_LIST_URL, params=params, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
            rows = payload.get("data", [])
            if not rows:
                continue
            for row in rows:
                svc_id = str(row.get("서비스ID", "")).strip()
                if not svc_id or svc_id in seen_svc:
                    continue
                seen_svc.add(svc_id)

                title = str(row.get("서비스명", "")).strip()
                org = str(row.get("소관기관명", "")).strip()
                org_type = str(row.get("소관기관유형", "") or "").strip()
                target_text = re.sub(r"\s+", " ", str(row.get("지원대상", "") or "").strip())
                benefit_text = re.sub(
                    r"\s+",
                    " ",
                    str(row.get("지원내용", "") or row.get("서비스목적요약", "") or "").strip(),
                )
                period_text = re.sub(r"\s+", " ", str(row.get("신청기한", "") or "상시 신청").strip())
                detail_url = str(row.get("상세조회URL", "") or "https://www.gov.kr").strip()
                category = str(row.get("서비스분야", "") or "정부/지자체지원").strip()

                # 본문 정보가 부실한 공고 스텁 제외
                if len(title) < 4 or len(target_text) < 8 or len(benefit_text) < 12:
                    continue

                start_dt, end_dt, is_always = extract_dates_from_text(period_text)
                region = "전국"
                if "중앙행정기관" in org_type or "공공기관" in org_type:
                    region = "전국"
                elif sido and sido in org:
                    region = sido
                elif "서울특별시" in org:
                    region = "서울"
                elif any(loc in org for loc in ["특별시", "광역시", "특별자치", "도", "시", "군", "구"]):
                    region = org

                results.append(
                    BenefitItem(
                        id=f"gov24_{svc_id}",
                        title=title,
                        category=category,
                        organization=org,
                        target_summary=target_text[:130],
                        summary=benefit_text[:150],
                        apply_period_text=period_text[:80],
                        start_date=start_dt,
                        end_date=end_dt,
                        is_always_open=is_always,
                        region=region,
                        url=detail_url,
                    )
                )
        except Exception as exc:
            print(f"[WARN] 보조금24 API 수집 중 오류 발생 (page={page}): {exc}")
            break

    return results
