from datetime import date
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from src.config_loader import calculate_age
from src.models import BenefitItem, ClassifiedBenefits

TELEGRAM_MAX_LEN = 4000


def _format_item_detailed(item: BenefitItem) -> str:
    star = "⭐ " if item.is_priority else "• "
    d_str = f" (D-{item.d_day})" if item.d_day is not None else (" (상시)" if item.is_always_open else "")
    lines = [
        f"{star}[{item.category}] {item.title}{d_str}",
        f"  - 기관: {item.organization} ({item.region})",
        f"  - 내용: {item.summary}",
        f"  - 기간: {item.apply_period_text}",
    ]
    if item.url:
        lines.append(f"  - 링크: {item.url}")
    return "\n".join(lines)


def _format_item_compact(item: BenefitItem) -> str:
    star = "⭐" if item.is_priority else "•"
    d_str = f"~{item.end_date} (D-{item.d_day})" if item.end_date and item.d_day is not None else item.apply_period_text
    link_part = f" | {item.url}" if item.url else ""
    return f"{star} [{item.category}] {item.title} ({d_str}){link_part}"


def format_daily_briefing(
    classified: ClassifiedBenefits,
    config: Dict[str, Any],
    today: Optional[date] = None,
) -> str:
    ref_today = today or date.today()
    profile = config.get("profile", {})
    notif = config.get("notification", {})
    max_other = int(notif.get("max_other_items_in_message", 20))

    age = calculate_age(profile.get("birth_year", 1995), ref_today)
    sido = profile.get("region_sido", "").strip()
    sigungu = profile.get("region_sigungu", "").strip()
    region_label = f"{sido} {sigungu}".strip() or "전국"

    header = [
        f"📢 [{ref_today.strftime('%Y-%m-%d')} 오늘의 맞춤 혜택 브리핑]",
        f"(필터 기준: 만 {age}세 / {region_label} + 전국 공통)",
        "─" * 28,
    ]
    sections: List[str] = ["\n".join(header)]

    if classified.newly_opened:
        sec = [f"🔥 1. 새로 발견/오픈한 혜택 ({len(classified.newly_opened)}건)"]
        for item in classified.newly_opened:
            sec.append(_format_item_detailed(item))
        sections.append("\n\n".join(sec))
    else:
        sections.append("🔥 1. 새로 발견/오픈한 혜택 (0건)\n• 오늘 새로 추가된 공고는 없습니다.")

    if classified.closing_soon:
        sec = [f"⏰ 2. 마감 임박 혜택 ({len(classified.closing_soon)}건)"]
        for item in classified.closing_soon:
            sec.append(_format_item_detailed(item))
        sections.append("\n\n".join(sec))

    if classified.currently_open:
        shown = classified.currently_open[:max_other]
        sec = [f"📌 3. 현재 신청 가능한 혜택 ({len(classified.currently_open)}건)"]
        for item in shown:
            sec.append(_format_item_compact(item))
        if len(classified.currently_open) > max_other:
            sec.append(f"  ...외 {len(classified.currently_open) - max_other}건")
        sections.append("\n".join(sec))

    if classified.upcoming_monthly:
        sec = [f"🗓️ 4. 이번 달·다음 달 오픈 예정 정기 혜택 ({len(classified.upcoming_monthly)}건)"]
        for item in classified.upcoming_monthly:
            sec.append(_format_item_compact(item))
        sections.append("\n".join(sec))

    return "\n\n".join(sections)


def split_message_chunks(text: str, max_length: int = TELEGRAM_MAX_LEN) -> List[str]:
    if len(text) <= max_length:
        return [text]

    chunks: List[str] = []
    current_lines: List[str] = []
    current_len = 0

    for line in text.split("\n"):
        if len(line) > max_length:
            if current_lines:
                chunks.append("\n".join(current_lines))
                current_lines = []
                current_len = 0
            for i in range(0, len(line), max_length):
                chunks.append(line[i : i + max_length])
            continue

        added_len = len(line) + (1 if current_lines else 0)
        if current_len + added_len > max_length:
            chunks.append("\n".join(current_lines))
            current_lines = [line]
            current_len = len(line)
        else:
            current_lines.append(line)
            current_len += added_len

    if current_lines:
        chunks.append("\n".join(current_lines))
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
        prefix = f"[{idx}/{len(chunks)}]\n" if len(chunks) > 1 else ""
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": prefix + chunk,
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        resp.raise_for_status()
    return True
