from datetime import date
import html
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from src.config_loader import calculate_age
from src.models import BenefitItem, ClassifiedBenefits

TELEGRAM_MAX_LEN = 3900


def _esc(text: str) -> str:
    return html.escape(str(text or ""), quote=True)


def _format_card_style_b(idx: int, item: BenefitItem) -> str:
    """시안 B: 항목 태그 카드형 (🎯대상 / 💰혜택 / 🗓기간 줄바꿈 정리 + 상세/신청 딥링크 버튼)"""
    btns = []
    if item.url and item.apply_url and item.url != item.apply_url:
        btns.append(f'<a href="{_esc(item.url)}">[📄상세안내]</a>')
        btns.append(f'<a href="{_esc(item.apply_url)}">[⚡신청창구]</a>')
    elif item.url:
        btns.append(f'<a href="{_esc(item.url)}">[📄상세·신청페이지]</a>')
    link_btn = (" " + " ".join(btns)) if btns else ""
    d_badge = f" (D-{item.d_day})" if item.d_day is not None else (" (상시)" if item.is_always_open else "")

    lines = [
        f"<b>{idx}. [{_esc(item.category)}] {_esc(item.title)}</b>{link_btn}",
        f"• 🎯 <b>대상</b>: {_esc(item.target_summary)}",
        f"• 💰 <b>혜택</b>: {_esc(item.summary)}",
        f"• 🗓 <b>기간</b>: {_esc(item.apply_period_text)}{_esc(d_badge)}",
    ]
    return "\n".join(lines)


def _format_news_line(item: BenefitItem) -> str:
    link_btn = f' <a href="{_esc(item.url)}">[기사↗]</a>' if item.url else ""
    return f"• {_esc(item.title)}{link_btn}"


def format_daily_briefing(
    classified: ClassifiedBenefits,
    config: Dict[str, Any],
    today: Optional[date] = None,
) -> str:
    ref_today = today or date.today()
    profile = config.get("profile", {})
    notif = config.get("notification", {})
    max_other = int(notif.get("max_other_items_in_message", 20))

    age = calculate_age(profile.get("birth_year", 1994), ref_today)
    sido = profile.get("region_sido", "").strip()
    sigungu = profile.get("region_sigungu", "").strip()
    region_label = f"{sido} {sigungu}".strip() or "전국"

    header = [
        f"📢 <b>[{ref_today.strftime('%Y-%m-%d')} 내 맞춤 혜택 브리핑]</b>",
        f"👤 기준: <b>만 {age}세 · {_esc(region_label)}</b> (+전국 공통)",
        "────────────────────",
    ]
    sections: List[str] = ["\n".join(header)]

    if classified.newly_opened:
        sec = [f"🔥 <b>1. 오늘 새로 추가된 혜택 ({len(classified.newly_opened)}건)</b>"]
        for idx, item in enumerate(classified.newly_opened, 1):
            sec.append(_format_card_style_b(idx, item))
        sections.append("\n\n".join(sec))

    if classified.closing_soon:
        sec = [f"⏰ <b>2. 마감 임박! 3일 내 종료 ({len(classified.closing_soon)}건)</b>"]
        for idx, item in enumerate(classified.closing_soon, 1):
            sec.append(_format_card_style_b(idx, item))
        sections.append("\n\n".join(sec))

    if classified.currently_open:
        shown = classified.currently_open[:max_other]
        sec = [f"📌 <b>3. 지금 바로 신청 가능한 혜택 ({len(classified.currently_open)}건)</b>"]
        for idx, item in enumerate(shown, 1):
            sec.append(_format_card_style_b(idx, item))
        sections.append("\n\n".join(sec))

    if classified.upcoming_monthly:
        sec = [f"🗓️ <b>4. 곧 오픈 예정인 정기 혜택 ({len(classified.upcoming_monthly)}건)</b>"]
        for idx, item in enumerate(classified.upcoming_monthly, 1):
            sec.append(_format_card_style_b(idx, item))
        sections.append("\n\n".join(sec))

    if classified.reference_news:
        sec = ["📰 <b>[참고] 최근 발표된 관련 정책 뉴스</b>"]
        for item in classified.reference_news:
            sec.append(_format_news_line(item))
        sections.append("\n".join(sec))

    return "\n\n".join(sections)


def split_message_chunks(text: str, max_length: int = TELEGRAM_MAX_LEN) -> List[str]:
    if len(text) <= max_length:
        return [text]

    chunks: List[str] = []
    current_blocks: List[str] = []
    current_len = 0

    # 카드 단위(\n\n)로 끊어서 HTML 태그가 중간에 잘리지 않도록 안전하게 분할
    for block in text.split("\n\n"):
        if len(block) > max_length:
            if current_blocks:
                chunks.append("\n\n".join(current_blocks))
                current_blocks = []
                current_len = 0
            lines = block.split("\n")
            temp_lines: List[str] = []
            temp_len = 0
            for ln in lines:
                add_l = len(ln) + (1 if temp_lines else 0)
                if temp_len + add_l > max_length and temp_lines:
                    chunks.append("\n".join(temp_lines))
                    temp_lines = [ln]
                    temp_len = len(ln)
                else:
                    temp_lines.append(ln)
                    temp_len += add_l
            if temp_lines:
                chunks.append("\n".join(temp_lines))
            continue

        added_len = len(block) + (2 if current_blocks else 0)
        if current_len + added_len > max_length:
            chunks.append("\n\n".join(current_blocks))
            current_blocks = [block]
            current_len = len(block)
        else:
            current_blocks.append(block)
            current_len += added_len

    if current_blocks:
        chunks.append("\n\n".join(current_blocks))
    return chunks


def _load_dotenv_fallback() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def send_telegram_message(text: str, preview_path: Optional[Path] = None) -> bool:
    if preview_path:
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_text(text, encoding="utf-8")

    _load_dotenv_fallback()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not bot_token or not chat_id:
        print("[INFO] TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되지 않아 로컬 프리뷰만 생성했습니다.")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chunks = split_message_chunks(text)

    for idx, chunk in enumerate(chunks, 1):
        prefix = f"<b>[{idx}/{len(chunks)}]</b>\n" if len(chunks) > 1 else ""
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": prefix + chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        resp.raise_for_status()
    return True


def send_telegram_blog_package(blog_pkg: Dict[str, Any]) -> bool:
    """오늘의 블로그 원고(.html 올인원 파일 + .md 텍스트 + 썸네일/인포그래픽 이미지 2장)를 텔레그램으로 전송"""
    _load_dotenv_fallback()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not bot_token or not chat_id:
        print("[INFO] 텔레그램 설정이 없어 블로그 패키지는 로컬 파일로만 저장했습니다.")
        return False

    base_api = f"https://api.telegram.org/bot{bot_token}"
    html_path: Path = blog_pkg["html_path"]
    md_path: Path = blog_pkg["md_path"]
    thumb_path: Path = blog_pkg["thumb_path"]
    info_path: Path = blog_pkg["info_path"]
    blog_cat: str = blog_pkg["blog_category"]
    rec_title: str = blog_pkg["recommended_title"]

    # 1. 썸네일 & 본문 인포그래픽 이미지 전송
    for label, img_p in [("🎨 [1/2] 블로그 대표 썸네일 이미지", thumb_path), ("📊 [2/2] 본문 삽입용 핵심 요약 인포그래픽", info_path)]:
        if img_p and img_p.exists():
            with open(img_p, "rb") as f:
                r = requests.post(
                    f"{base_api}/sendPhoto",
                    data={"chat_id": chat_id, "caption": label},
                    files={"photo": (img_p.name, f, "image/png")},
                    timeout=25,
                )
                r.raise_for_status()

    # 2. 이미지 내장 올인원 HTML 파일 전송
    caption_html = (
        f"📝 [오늘의 혜택 블로그 올인원 원고]\n"
        f"• 📂 카테고리: {blog_cat}\n"
        f"• 💡 추천제목: {rec_title}\n\n"
        f"👉 위 .html 파일을 열면 [이미지 2장 포함 + 본문 서식 1클릭 복사]가 바로 가능합니다!"
    )
    if html_path and html_path.exists():
        with open(html_path, "rb") as f:
            r = requests.post(
                f"{base_api}/sendDocument",
                data={"chat_id": chat_id, "caption": caption_html},
                files={"document": (html_path.name, f, "text/html")},
                timeout=25,
            )
            r.raise_for_status()

    # 3. 순수 텍스트(.md) 원고 파일도 함께 전송
    if md_path and md_path.exists():
        with open(md_path, "rb") as f:
            r = requests.post(
                f"{base_api}/sendDocument",
                data={"chat_id": chat_id, "caption": f"📄 [순수 텍스트 복붙용 원고] ({blog_cat})"},
                files={"document": (md_path.name, f, "text/plain")},
                timeout=25,
            )
            r.raise_for_status()

    return True
