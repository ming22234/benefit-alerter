from datetime import date
from email.utils import parsedate_to_datetime
import re
from typing import List
from urllib.parse import quote
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from src.models import BenefitItem

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

OTHER_REGIONS_REGEX = re.compile(
    r"([가-힣]{1,4}(?:특별시|광역시|특별자치시|특별자치도|시|군|구)|서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)"
)


def detect_region_from_title(title: str, default_region: str = "전국") -> str:
    matches = OTHER_REGIONS_REGEX.findall(title)
    stopwords = {
        "지원시", "신청시", "모집시", "접수시", "선발시", "교육구", "청년구",
        "가구", "창구", "도구", "연구", "신규", "전구", "인구", "요구", "복구",
        "청구", "탐구", "추구", "지구", "출구", "입구", "문구", "식구", "수구",
        "구구", "시시", "일시", "동시", "상시", "수시", "정시", "임시", "출시",
        "실시", "개시", "표시", "무시", "응시", "시군", "시도", "시군구",
    }
    valid = [m for m in matches if m not in stopwords and len(m) >= 2]
    if valid:
        return " ".join(dict.fromkeys(valid))
    return default_region


def scrape_wevity_scholarships_and_support() -> List[BenefitItem]:
    """위비티(Wevity) 장학금/지원금/청년혜택/교육 공모 리스트 실시간 수집 (API 키 불필요)"""
    urls = [
        "https://www.wevity.com/?c=find&s=1&gub=1",
        "https://www.wevity.com/?c=active&s=1",
    ]
    items: List[BenefitItem] = []
    seen_local = set()
    keywords = ["장학", "지원금", "바우처", "이용권", "청년", "적금", "교육", "무료", "국비", "수당", "월세", "아카데미", "취업"]
    today = date.today()

    for url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=12)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("ul.list li")

            for row in rows:
                if "top" in (row.get("class") or []):
                    continue
                tit_el = row.select_one("div.tit a")
                organ_el = row.select_one("div.organ")
                day_el = row.select_one("div.day")
                if not tit_el:
                    continue

                raw_title = re.sub(r"\s+(SPECIAL|IDEA|NEW|HOT)\b", "", tit_el.get_text(" ", strip=True)).strip()
                href = tit_el.get("href", "")
                org = organ_el.get_text(strip=True) if organ_el else "민간/공공기관"
                day_text = day_el.get_text(" ", strip=True) if day_el else ""

                if not any(kw in raw_title for kw in keywords):
                    continue

                d_match = re.search(r"D-(\d+)", day_text)
                end_date_str = None
                if d_match:
                    d_val = int(d_match.group(1))
                    end_dt = date.fromordinal(today.toordinal() + d_val)
                    end_date_str = end_dt.strftime("%Y-%m-%d")
                elif "오늘마감" in day_text or "D-day" in day_text:
                    end_date_str = today.strftime("%Y-%m-%d")
                else:
                    continue

                ix_match = re.search(r"ix=(\d+)", href)
                item_id = f"wevity_{ix_match.group(1)}" if ix_match else f"wevity_{abs(hash(raw_title)) % 1000000}"
                if item_id in seen_local:
                    continue
                seen_local.add(item_id)

                detail_url = f"https://www.wevity.com/{href.lstrip('/')}" if href else url
                detected_region = detect_region_from_title(f"{raw_title} {org}", default_region="전국")

                items.append(
                    BenefitItem(
                        id=item_id,
                        title=raw_title,
                        category="민간/장학·대외활동",
                        organization=org,
                        summary=f"{org} 주관 교육/장학/대외활동 지원 공고",
                        apply_period_text=f"마감 {day_text}" if day_text else "진행중",
                        end_date=end_date_str,
                        is_always_open=False,
                        region=detected_region,
                        url=detail_url,
                    )
                )
        except Exception as exc:
            print(f"[WARN] 위비티 혜택 크롤링 실패 ({url}): {exc}")

    return items


def scrape_policy_news_rss(sido: str = "", sigungu: str = "") -> List[BenefitItem]:
    """정부/지자체 신규 지원금·바우처·청년적금 신청 오픈 소식을 실시간 뉴스 RSS로 서치 (API 키 불필요)"""
    loc_parts = [p.strip() for p in [sido, *sigungu.split()] if p.strip()]
    region_or_expr = " OR ".join(loc_parts) if loc_parts else "정부"
    queries = [
        ("교육/바우처", "평생교육이용권 OR 평생교육바우처 OR 내일배움카드 신청 모집"),
        ("청년/금융", "청년도약계좌 OR 청년내일저축계좌 OR 청년월세지원 신청 접수"),
        ("지자체지원", f"({region_or_expr}) (지원금 OR 바우처 OR 응시료 OR 장학금 OR 청년) (신청 OR 모집 OR 접수)"),
    ]
    noise_words = [
        "급감", "반납", "논란", "단독", "사기", "주의보", "구속", "적발", "폐지",
        "국정감사", "국감", "미집행", "감소", "경신", "돌파", "마감된", "종료된", "중단", "잔혹사",
    ]
    action_words = ["신청", "모집", "접수", "오픈", "개시", "발급"]

    items: List[BenefitItem] = []
    seen_titles = set()
    today = date.today()

    for category, q in queries:
        rss_url = f"https://news.google.com/rss/search?q={quote(q + ' when:7d')}&hl=ko&gl=KR&ceid=KR:ko"
        try:
            resp = requests.get(rss_url, headers=HEADERS, timeout=12)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            for item_el in root.findall("./channel/item")[:8]:
                raw_title = (item_el.findtext("title") or "").strip()
                link = (item_el.findtext("link") or "").strip()
                pub_date_raw = (item_el.findtext("pubDate") or "").strip()
                source_el = item_el.find("source")
                source_name = source_el.text.strip() if source_el is not None and source_el.text else "정책/공고 소식"

                clean_title = re.sub(r"\s*-\s*[^-]+$", "", raw_title).strip()
                if not clean_title or clean_title in seen_titles:
                    continue
                if any(nw in clean_title for nw in noise_words):
                    continue
                if not any(aw in clean_title for aw in action_words):
                    continue
                seen_titles.add(clean_title)

                pub_dt_str = today.strftime("%Y-%m-%d")
                if pub_date_raw:
                    try:
                        pub_dt_str = parsedate_to_datetime(pub_date_raw).date().strftime("%Y-%m-%d")
                    except Exception:
                        pass

                default_reg = f"{sido} {sigungu}".strip() if category == "지자체지원" and sido else "전국"
                detected_region = detect_region_from_title(clean_title, default_region=default_reg)
                item_id = f"news_{abs(hash(clean_title)) % 10000000}"

                items.append(
                    BenefitItem(
                        id=item_id,
                        title=clean_title,
                        category=category,
                        organization=source_name,
                        summary="최근 7일 내 발표된 신규 신청/모집 공고 소식",
                        apply_period_text=f"공고 발표일: {pub_dt_str} (상세 일정 링크 확인)",
                        start_date=pub_dt_str,
                        is_always_open=True,
                        region=detected_region,
                        url=link,
                    )
                )
        except Exception as exc:
            print(f"[WARN] 정책 뉴스 RSS 수집 실패 ({category}): {exc}")

    return items
