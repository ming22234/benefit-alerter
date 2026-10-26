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


def collect_gov24_benefits(sido: str = "", max_pages: int = 2) -> List[BenefitItem]:
    api_key = os.getenv("DATA_GO_KR_API_KEY", "").strip()
    if not api_key:
        return []

    results: List[BenefitItem] = []
    for page in range(1, max_pages + 1):
        params = {
            "serviceKey": api_key,
            "page": page,
            "perPage": 50,
            "returnType": "JSON",
        }
        try:
            resp = requests.get(GOV24_SERVICE_LIST_URL, params=params, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
            rows = payload.get("data", [])
            for row in rows:
                svc_id = str(row.get("서비스ID", "")).strip()
                title = str(row.get("서비스명", "")).strip()
                org = str(row.get("소관기관명", "")).strip()
                target_text = str(row.get("지원대상", "") or "상세 공고 참조").strip()
                benefit_text = str(row.get("지원내용", "") or row.get("서비스목적요약", "")).strip()
                period_text = str(row.get("신청기한", "") or "상시").strip()
                detail_url = str(row.get("상세조회URL", "") or "https://www.gov.kr").strip()
                category = str(row.get("서비스분야", "") or "정부/지자체지원").strip()

                start_dt, end_dt, is_always = extract_dates_from_text(period_text)
                region = "전국"
                if any(loc in org for loc in ["시", "도", "군", "구"]) and "부" not in org and "청" not in org:
                    region = org

                results.append(
                    BenefitItem(
                        id=f"gov24_{svc_id}",
                        title=title,
                        category=category,
                        organization=org,
                        target_summary=re.sub(r"\s+", " ", target_text)[:100],
                        summary=re.sub(r"\s+", " ", benefit_text)[:120],
                        apply_period_text=period_text,
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
