import base64
from datetime import date
import hashlib
import html
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests

from src.blog_image_generator import (
    THEME_ORDER,
    generate_benefit_infographic,
    generate_benefit_thumbnail,
)
from src.blog_picker import (
    BLOG_HISTORY_PATH,
    load_blog_history,
    pick_candidates,
    save_blog_history,
)

BASE_DIR = Path(__file__).resolve().parent.parent
BLOG_DIR = BASE_DIR / "blog_posts"
IMG_DIR = BLOG_DIR / "images"

FORMAT_ORDER = (
    "F1_QA",
    "F2_STEP_GUIDE",
    "F3_CHECKLIST",
    "F4_BRIEFING",
    "F5_TIMING_TIP",
)

FORMAT_LABELS = {
    "F1_QA": "Q&A 문답 풀이형 (친근한 해요체)",
    "F2_STEP_GUIDE": "단계별 실전 가이드형 (깔끔한 안내체)",
    "F3_CHECKLIST": "자가진단 체크리스트형 (부드러운 블로그체)",
    "F4_BRIEFING": "핵심 요약 브리핑형 (단정한 노트체)",
    "F5_TIMING_TIP": "일정·꿀팁 집중형 (경쾌한 생활정보체)",
}


def map_blog_category(item_category: str, title: str) -> str:
    """mingtip 블로그 실제 4대 카테고리(돈·지원금 / 건강·접종 / 살림·생활 / 폰·행정) 정확 매핑"""
    combined = f"{item_category} {title}"
    if any(k in combined for k in ["건강", "접종", "검진", "백신", "의료", "병원", "치료", "치매", "심리", "마음", "임신"]):
        return "건강·접종"
    if any(k in combined for k in ["모바일", "신분증", "주민등록증", "운전면허", "민원", "등본", "통신", "선택약정", "스마트초이스", "어카운트인포", "채권"]):
        return "폰·행정"
    if any(k in combined for k in ["패스", "교통", "전기", "가스", "수도", "난방", "에너지", "탄소중립", "온누리", "가전", "자동차세", "전월세"]):
        return "살림·생활"
    return "돈·지원금"


def _encode_png_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _extract_short_amount(summary: str) -> str:
    m = re.search(
        r"((?:연\s*|월\s*)?(?:최대\s*)?\d[\d,]*\s*(?:만\s*원|원)|\d{1,2}\s*~\s*\d{1,2}%|\d{1,3}%)",
        summary or "",
    )
    if m:
        val = re.sub(r"\s+", " ", m.group(1)).strip()
        if "%" in val and "할인" in (summary or ""):
            return f"{val} 요금 할인"
        if "%" in val and "환급" in (summary or ""):
            return f"{val} 환급 혜택"
        return f"{val} 지원 혜택"
    if "무료" in (summary or ""):
        return "전액 무료 지원"
    return "핵심 지원 혜택"


def _clean_short_title(title: str) -> str:
    s = re.sub(r"^\[[^\]]+\]\s*", "", title or "")
    s = re.sub(r"\s*\([^)]*\)", "", s).strip()
    return s


def _pick_next_rotation(
    history: List[Dict[str, Any]],
    today: date,
    benefit_id: str,
) -> Tuple[str, str]:
    """직전 글과 같은 포맷·테마가 연속으로 나오지 않도록 순환 선택한다."""
    last_fmt = str(history[-1].get("format_id") or "") if history else ""
    last_thm = str(history[-1].get("theme_id") or "") if history else ""

    seed_num = int(hashlib.md5(f"{today.isoformat()}:{benefit_id}".encode("utf-8")).hexdigest()[:8], 16)
    fmt_idx = (len(history) + seed_num) % len(FORMAT_ORDER)
    if FORMAT_ORDER[fmt_idx] == last_fmt:
        fmt_idx = (fmt_idx + 1) % len(FORMAT_ORDER)

    thm_idx = (len(history) + (seed_num // 7)) % len(THEME_ORDER)
    if THEME_ORDER[thm_idx] == last_thm:
        thm_idx = (thm_idx + 1) % len(THEME_ORDER)

    return FORMAT_ORDER[fmt_idx], THEME_ORDER[thm_idx]


def _build_titles(
    short_name: str,
    amount_highlight: str,
    blog_cat: str,
    period_text: str,
    format_id: str,
) -> List[str]:
    """포맷별로 대표 추천 제목 공식이 달라지도록 4가지 자연스러운 검색형 제목 생성"""
    has_deadline = any(k in period_text for k in ["까지", "~", "마감", "분기", "절기"])
    t_qa = f"{short_name} 신청 조건과 대상은? {amount_highlight} 받는 방법 정리"
    t_step = f"{short_name} 온라인 신청 방법과 자격 기준 ({amount_highlight})"
    t_check = (
        f"{short_name} 신청 기간 놓치지 마세요, 대상 조회부터 접수 순서까지"
        if has_deadline
        else f"놓치기 쉬운 {short_name}, {amount_highlight} 대상 조회와 신청 순서"
    )
    t_brief = f"{short_name} 자격 요건부터 {amount_highlight} 지급 기준까지 한눈에 정리"

    ordered_map = {
        "F1_QA": [t_qa, t_step, t_check],
        "F2_STEP_GUIDE": [t_step, t_brief, t_qa],
        "F3_CHECKLIST": [t_check, t_qa, t_step],
        "F4_BRIEFING": [t_brief, t_step, t_check],
        "F5_TIMING_TIP": [t_check, t_brief, t_qa],
    }
    return ordered_map.get(format_id, [t_qa, t_step, t_check])


def _build_hashtags(short_name: str, org: str, blog_cat: str, region_label: str) -> List[str]:
    """주제·카테고리와 실제로 일치하는 태그만 생성(#청년지원금 무분별 삽입 금지)"""
    tags: List[str] = []

    def add(raw: str) -> None:
        cleaned = re.sub(r"[^가-힣a-zA-Z0-9]", "", raw or "")
        if len(cleaned) >= 2 and f"#{cleaned}" not in tags:
            tags.append(f"#{cleaned}")

    add(short_name)
    for token in re.split(r"[·/\s]+", short_name):
        if len(token) >= 3:
            add(token)

    for org_part in re.split(r"[·()\s]+", org):
        if len(org_part) >= 3 and org_part not in ("경기도", "전국", "시군"):
            add(org_part)

    if "경기" in region_label:
        add("경기도지원사업")
    elif "서울" in region_label:
        add("서울시지원사업")

    cat_tags = {
        "건강·접종": ["건강정보", "무료검진", "의료비지원", "국민건강보험", "생활건강꿀팁"],
        "폰·행정": ["숨은돈찾기", "환급금조회", "통신비절약", "생활행정꿀팁", "모바일신청"],
        "살림·생활": ["생활비절약", "고정지출줄이기", "교통비환급", "공과금할인", "살림꿀팁"],
        "돈·지원금": ["정부지원금", "지원금신청방법", "복지로", "보조금24", "생활금융정보"],
    }
    for ct in cat_tags.get(blog_cat, cat_tags["돈·지원금"]):
        add(ct)

    return tags[:10]


def _pick_variant(variants: List[str], key: str) -> str:
    idx = int(hashlib.md5(key.encode("utf-8")).hexdigest()[:6], 16) % len(variants)
    return variants[idx]


def _try_gemini_custom_sections(
    *,
    format_id: str,
    short_name: str,
    org: str,
    region_label: str,
    target_text: str,
    benefit_text: str,
    period_text: str,
    blog_cat: str,
) -> Optional[Dict[str, str]]:
    """GEMINI_API_KEY 설정 시 매번 새로운 한국어 블로거 문장으로 도입·해설·마무리를 생성(실패·미설정 시 None 폴백)"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    tone_desc = (
        "친근하고 자연스러운 한국어 해요체(~해요, ~거든요, ~더라고요, ~죠를 골고루 섞음)"
        if format_id in ("F1_QA", "F3_CHECKLIST", "F5_TIMING_TIP")
        else "단정하고 읽기 편한 한국어 정보 블로거 문체(~합니다, ~해보세요, ~유리합니다)"
    )
    prompt = (
        f"한국 네이버 생활정보 블로그 '밍팁 노트'({blog_cat}) 원고의 핵심 문단을 작성해 주세요.\n"
        f"- 문체: {tone_desc}. '안녕하세요', '이 글에서는', '저라면 ~할 것 같아요', 이모지 남발, 지어낸 1인칭 경험담 절대 금지.\n"
        f"- 제공된 사실 밖의 숫자·조건은 절대 추측하거나 덧붙이지 마세요.\n"
        f"- 제도명: {short_name}\n"
        f"- 주관기관/지역: {org} / {region_label}\n"
        f"- 지원대상: {target_text}\n"
        f"- 지원내용: {benefit_text}\n"
        f"- 신청기간: {period_text}\n\n"
        "아래 JSON 키 4개만 정확히 반환하세요(각 값은 2~3문장, 줄바꿈은 \\n 사용):\n"
        '{"intro": "도입 공감 및 핵심 화두", "target_comment": "지원대상 확인 시 체크할 점", '
        '"benefit_comment": "혜택 활용 실용 조언", "closing": "마무리 당부 한마디"}'
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    try:
        resp = requests.post(
            url,
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7},
            },
            timeout=20,
        )
        resp.raise_for_status()
        cand_txt = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(cand_txt)
        if all(isinstance(parsed.get(k), str) and len(parsed[k].strip()) >= 15 for k in ("intro", "target_comment", "benefit_comment", "closing")):
            return {k: parsed[k].strip() for k in ("intro", "target_comment", "benefit_comment", "closing")}
    except Exception as exc:
        print(f"[INFO] Gemini 문장 생성 생략/폴백 ({exc})")
    return None


def _render_body_by_format(
    *,
    format_id: str,
    short_name: str,
    raw_title: str,
    org: str,
    region_label: str,
    target_text: str,
    benefit_text: str,
    period_text: str,
    detail_url: str,
    apply_url: str,
    blog_cat: str,
    thumb_b64: str,
    info_b64: str,
    hashtag_str: str,
    today_str: str,
    ai_sections: Optional[Dict[str, str]] = None,
) -> str:
    """5가지 서로 다른 글 뼈대·문체·표 배치로 렌더링하여 문서 간 유사도(shingle 중복)를 원천 해소한다."""
    esc = lambda s: html.escape(str(s or ""), quote=True)
    nl2br = lambda s: "<br>".join(esc(line.strip()) for line in str(s).splitlines() if line.strip())
    vkey = f"{today_str}:{short_name}:{blog_cat}"

    cat_intros_polite = {
        "건강·접종": [
            f"바쁘게 지내다 보면 무료로 챙길 수 있는 건강 지원이나 검진 시기를 깜빡 넘기기 쉬워요.\n이번에 정리해 보는 <b>{esc(short_name)}</b> 역시 대상자임에도 안내를 못 보고 지나치는 분들이 꽤 많더라고요.",
            f"병원비나 예방접종·검진 비용은 미리 제도를 알아두는 것만으로도 부담이 확 줄어들죠.\n오늘은 <b>{esc(org)}</b>에서 운영하는 <b>{esc(short_name)}</b> 대상 기준과 이용 방법을 핵심만 짚어볼게요.",
        ],
        "폰·행정": [
            f"스마트폰이나 온라인 조회 몇 번만 해봐도 아낄 수 있는 요금이나 돌려받을 수 있는 숨은 돈이 의외로 많아요.\n그중에서도 당장 확인해 두면 좋은 <b>{esc(short_name)}</b> 조회 기준과 신청 순서를 가져왔어요.",
            f"따로 서류를 떼러 관공서에 가지 않아도 모바일로 3분이면 끝나는 알짜 행정·통신 제도가 있죠.\n바로 <b>{esc(short_name)}</b>인데, 누가 어떻게 이용할 수 있는지 차근차근 풀어볼게요.",
        ],
        "살림·생활": [
            f"매달 나가는 교통비나 공과금, 장바구니 지출은 한 번만 할인·환급 구조를 세팅해 두면 일 년 내내 체감이 크더라고요.\n실생활에서 바로 쓰기 좋은 <b>{esc(short_name)}</b> 조건과 신청 팁을 모았습니다.",
            f"생활비 절약은 거창한 재테크보다 내가 해당되는 환급·바우처 제도를 제때 등록하는 데서 시작되죠.\n<b>{esc(short_name)}</b> 혜택을 빠짐없이 챙기는 방법을 살펴볼게요.",
        ],
        "돈·지원금": [
            f"신청 자격을 갖추고도 접수 기간이나 정확한 요건을 몰라 그냥 지나치는 지원 제도가 매년 적지 않아요.\n이번에는 <b>{esc(short_name)}</b> 대상 조건부터 실제 지원 내용까지 헷갈리기 쉬운 부분을 풀어볼게요.",
            f"정부나 지자체 지원사업은 공고문이 길어 보여도 내 나이·거주지·소득 기준 세 가지만 대조해 보면 금방 답이 나와요.\n<b>{esc(short_name)}</b> 핵심 기준을 보기 편하게 정리했습니다.",
        ],
    }

    cat_intros_formal = {
        "건강·접종": [
            f"시기만 잘 맞춰 챙겨도 본인 부담을 크게 덜 수 있는 대표적인 보건·의료 지원 제도가 바로 <b>'{esc(short_name)}'</b>입니다.\n{esc(org)} 기준 대상자 요건과 이용 절차를 핵심 위주로 정리합니다.",
        ],
        "폰·행정": [
            f"복잡한 서류 발급 없이 온라인 본인 인증만으로 간편하게 조회·신청할 수 있는 <b>'{esc(short_name)}'</b> 이용 가이드입니다.\n적용 대상과 신청 경로를 순서대로 확인해 보세요.",
        ],
        "살림·생활": [
            f"매월 반복되는 고정 생활비 부담을 줄이는 데 직접적인 도움이 되는 <b>'{esc(short_name)}'</b> 안내입니다.\n지원 범위와 등록 방법을 미리 확인해 두시기 바랍니다.",
        ],
        "돈·지원금": [
            f"요건에 부합한다면 기한 내에 꼭 확인해 두어야 할 <b>'{esc(short_name)}'</b> 핵심 정리입니다.\n지원 자격, 지급 혜택, 공식 신청 경로를 단계별로 살펴보겠습니다.",
        ],
    }

    thumb_block = (
        f'<p style="text-align:center; margin:0 0 24px 0;">'
        f'<img src="data:image/png;base64,{thumb_b64}" alt="{esc(short_name)} 안내 썸네일" '
        f'style="max-width:100%; width:640px; height:auto; border-radius:14px; border:1px solid #e2e8f0;">'
        f"</p>"
    )
    info_block = (
        f'<p style="text-align:center; margin:24px 0 28px 0;">'
        f'<img src="data:image/png;base64,{info_b64}" alt="{esc(short_name)} 요약표" '
        f'style="max-width:100%; width:680px; height:auto; border-radius:14px; border:1px solid #e2e8f0;">'
        f"</p>"
    )

    primary_link = apply_url or detail_url
    link_card = f"""
    <div style="background:#f8fafc; border:1px solid #cbd5e1; border-radius:12px; padding:16px 20px; margin:20px 0; font-size:15px; line-height:1.8;">
      <strong>공식 안내 및 온라인 신청 창구</strong><br>
      • 주관 기관 : {esc(org)} ({esc(region_label)})<br>
      • 바로가기 : <a href="{esc(primary_link)}" target="_blank" style="color:#2563eb; font-weight:bold;">공식 홈페이지 상세 안내 확인하기</a>
    </div>
    """

    # -------------------- F1: Q&A 문답형 (해요체)
    if format_id == "F1_QA":
        intro_html = nl2br(ai_sections["intro"]) if ai_sections else nl2br(_pick_variant(cat_intros_polite.get(blog_cat, cat_intros_polite["돈·지원금"]), vkey))
        t_comm = nl2br(ai_sections["target_comment"]) if ai_sections else "주민등록상 연령이나 지역·자격 기준이 공고일 기준으로 맞는지 먼저 대조해 보면 헛걸음을 줄일 수 있어요."
        b_comm = nl2br(ai_sections["benefit_comment"]) if ai_sections else "현금 지급인지, 바우처 포인트 차감인지에 따라 사용처나 입금 시기가 달라지니 미리 확인해 두면 훨씬 편하거든요."
        closing = nl2br(ai_sections["closing"]) if ai_sections else f"신청 일정이 <b>{esc(period_text)}</b>로 안내되어 있으니 미루지 말고 대상 여부부터 가볍게 조회해 보세요!"

        return f"""
    {thumb_block}
    <p style="font-size:16px; line-height:1.9;">{intro_html}</p>
    <br>
    <h3 style="font-size:19px; color:#1e293b; border-bottom:2px solid #3b82f6; padding-bottom:8px;">Q1. 누가 신청할 수 있나요?</h3>
    <div style="background:#eff6ff; border-radius:12px; padding:16px 20px; margin:14px 0; font-size:16px; line-height:1.85;">
      <strong>지원 대상 기준</strong><br>{esc(target_text)}<br>
      <span style="font-size:14px; color:#475569;">• 적용 범위 : {esc(region_label)} / 주관 : {esc(org)}</span>
    </div>
    <p style="font-size:16px; line-height:1.9;">{t_comm}</p>
    {info_block}
    <h3 style="font-size:19px; color:#1e293b; border-bottom:2px solid #3b82f6; padding-bottom:8px;">Q2. 어떤 혜택을 얼마나 받게 되나요?</h3>
    <p style="font-size:16px; line-height:1.9;">대상자로 확인되면 지원되는 핵심 내용은 아래와 같아요.</p>
    <blockquote style="margin:14px 0; padding:14px 18px; border-left:4px solid #10b981; background:#f0fdf4; font-size:16px; line-height:1.85;">
      <strong>{esc(benefit_text)}</strong>
    </blockquote>
    <p style="font-size:16px; line-height:1.9;">{b_comm}</p>
    <br>
    <h3 style="font-size:19px; color:#1e293b; border-bottom:2px solid #3b82f6; padding-bottom:8px;">Q3. 신청 기간과 접수 방법은 어떻게 되나요?</h3>
    <p style="font-size:16px; line-height:1.9;">
      접수 일정은 <strong>{esc(period_text)}</strong> 기준이에요.<br>
      온라인 본인 인증(간편인증·공동인증서)을 준비해 공식 접수 페이지에서 신청서를 작성하면 빠르게 마칠 수 있습니다.
    </p>
    {link_card}
    <p style="font-size:16px; line-height:1.9;">{closing}</p>
    <br>
    <p style="font-size:14px; color:#64748b;">{esc(hashtag_str)}</p>
"""

    # -------------------- F2: 단계별 실전 가이드형 (안내체)
    if format_id == "F2_STEP_GUIDE":
        intro_html = nl2br(ai_sections["intro"]) if ai_sections else nl2br(_pick_variant(cat_intros_formal.get(blog_cat, cat_intros_formal["돈·지원금"]), vkey))
        t_comm = nl2br(ai_sections["target_comment"]) if ai_sections else "연령·거주지 또는 소득 구간 요건이 있는 사업은 신청 페이지의 자격 자가진단이나 마이데이터 조회로 빠르게 판별할 수 있습니다."
        b_comm = nl2br(ai_sections["benefit_comment"]) if ai_sections else "지원 한도와 지급 주기는 세부 유형에 따라 차이가 있을 수 있으므로 본인에게 해당하는 기준을 꼭 대조해 보시기 바랍니다."
        closing = nl2br(ai_sections["closing"]) if ai_sections else "예산 한도가 있는 지원사업은 마감일 전이라도 조기에 종료될 수 있으니, 조건이 맞다면 여유 있게 신청을 마쳐 두세요."

        return f"""
    {thumb_block}
    <p style="font-size:16px; line-height:1.9;">{intro_html}</p>
    <table style="width:100%; border-collapse:collapse; margin:20px 0; font-size:15px;">
      <tbody>
        <tr><td style="width:25%; background:#1e293b; color:#fff; padding:11px 14px; border:1px solid #cbd5e1; font-weight:bold;">제도명</td><td style="padding:11px 14px; border:1px solid #cbd5e1;"><strong>{esc(raw_title)}</strong></td></tr>
        <tr><td style="background:#f8fafc; padding:11px 14px; border:1px solid #cbd5e1; font-weight:bold;">주관 / 지역</td><td style="padding:11px 14px; border:1px solid #cbd5e1;">{esc(org)} ({esc(region_label)})</td></tr>
        <tr><td style="background:#f8fafc; padding:11px 14px; border:1px solid #cbd5e1; font-weight:bold;">신청 일정</td><td style="padding:11px 14px; border:1px solid #cbd5e1;"><strong>{esc(period_text)}</strong></td></tr>
      </tbody>
    </table>
    <br>
    <h3 style="font-size:20px; color:#0f172a; border-left:5px solid #2563eb; padding-left:12px;">STEP 1. 지원 대상 요건 확인</h3>
    <p style="font-size:16px; line-height:1.9;">
      첫 순서로 본인이 수혜 대상에 해당하는지 확인합니다.<br>
      공식 안내된 대상 기준은 <strong>{esc(target_text)}</strong>입니다.
    </p>
    <p style="font-size:16px; line-height:1.9;">{t_comm}</p>
    <br>
    <h3 style="font-size:20px; color:#0f172a; border-left:5px solid #2563eb; padding-left:12px;">STEP 2. 지원 금액 및 혜택 범위</h3>
    <p style="font-size:16px; line-height:1.9;">
      선정 및 승인 완료 시 제공되는 핵심 혜택은 <strong>{esc(benefit_text)}</strong>입니다.<br>
      {b_comm}
    </p>
    {info_block}
    <h3 style="font-size:20px; color:#0f172a; border-left:5px solid #2563eb; padding-left:12px;">STEP 3. 온라인 접수 순서</h3>
    <p style="font-size:16px; line-height:1.9;">
      1) 아래 공식 접수처 접속 및 간편·공동인증서 로그인<br>
      2) 대상자 조회 및 신청 정보 입력 (행정정보 공동이용 동의 시 기본 서류 간소화)<br>
      3) 추가 구비서류 해당 여부 확인 후 최종 제출
    </p>
    {link_card}
    <p style="font-size:16px; line-height:1.9;">{closing}</p>
    <br>
    <p style="font-size:14px; color:#64748b;">{esc(hashtag_str)}</p>
"""

    # -------------------- F3: 자가진단 체크리스트형 (부드러운 에세이체)
    if format_id == "F3_CHECKLIST":
        intro_html = nl2br(ai_sections["intro"]) if ai_sections else nl2br(_pick_variant(cat_intros_polite.get(blog_cat, cat_intros_polite["돈·지원금"]), vkey + ":c"))
        t_comm = nl2br(ai_sections["target_comment"]) if ai_sections else "위 세 줄만 먼저 맞춰 봐도 내가 신청 가능한지 대략적인 윤곽이 바로 잡히죠."
        b_comm = nl2br(ai_sections["benefit_comment"]) if ai_sections else "한 번 신청해 두면 생활비나 필수 비용을 아끼는 데 꽤 쏠쏠하게 보탬이 되더라고요."
        closing = nl2br(ai_sections["closing"]) if ai_sections else "주변 가족이나 지인 중에서도 해당될 만한 분이 있다면 함께 알려주셔도 좋을 것 같아요!"

        return f"""
    {thumb_block}
    <p style="font-size:16px; line-height:1.9;">{intro_html}</p>
    <div style="background:#fffbeb; border:1px solid #fde68a; border-radius:14px; padding:18px 22px; margin:20px 0; font-size:16px; line-height:1.9;">
      <strong>신청 전 3초 체크리스트</strong><br>
      ✔ <b>대상 요건</b> : {esc(target_text)}<br>
      ✔ <b>지역 범위</b> : {esc(region_label)}<br>
      ✔ <b>신청 일정</b> : {esc(period_text)}
    </div>
    <p style="font-size:16px; line-height:1.9;">{t_comm}</p>
    <br>
    <h3 style="font-size:19px; color:#7c2d12; border-left:5px solid #ea580c; padding-left:12px;">어떤 혜택이 주어질까요?</h3>
    <p style="font-size:16px; line-height:1.9;">
      <strong>{esc(short_name)}</strong>의 핵심 지원 내용은 <strong>{esc(benefit_text)}</strong>이에요.<br>
      {b_comm}
    </p>
    {info_block}
    <h3 style="font-size:19px; color:#7c2d12; border-left:5px solid #ea580c; padding-left:12px;">어디서 신청하고 무엇을 조심해야 할까요?</h3>
    <p style="font-size:16px; line-height:1.9;">
      주관 기관인 <strong>{esc(org)}</strong>의 온라인 접수 창구에서 본인 인증 후 신청할 수 있어요.<br>
      접수 마감일 직전에는 접속자가 몰리거나 서류 보완 시간이 부족할 수 있으니 일정 여유를 두고 접수해 두시는 편이 안전합니다.
    </p>
    {link_card}
    <p style="font-size:16px; line-height:1.9;">{closing}</p>
    <br>
    <p style="font-size:14px; color:#64748b;">{esc(hashtag_str)}</p>
"""

    # -------------------- F4: 핵심 요약 브리핑형 (단정한 노트체)
    if format_id == "F4_BRIEFING":
        intro_html = nl2br(ai_sections["intro"]) if ai_sections else nl2br(_pick_variant(cat_intros_formal.get(blog_cat, cat_intros_formal["돈·지원금"]), vkey + ":b"))
        t_comm = nl2br(ai_sections["target_comment"]) if ai_sections else "세부 가구원 수나 소득·자격 인정 기준은 주관 기관의 최신 공고문을 기준으로 심사됩니다."
        b_comm = nl2br(ai_sections["benefit_comment"]) if ai_sections else "동일 성격의 타 사업과 중복 수혜가 제한되는 경우가 있으므로 신청 단계의 유의사항 안내를 함께 살펴보시는 것이 좋습니다."
        closing = nl2br(ai_sections["closing"]) if ai_sections else f"지금까지 '{esc(short_name)}'의 주요 자격과 신청 방법을 정리해 드렸습니다. 대상 요건에 해당한다면 기한 내 꼭 활용해 보세요."

        return f"""
    {thumb_block}
    <div style="background:#f1f5f9; border-radius:12px; padding:18px 22px; margin:0 0 22px 0; font-size:15px; line-height:1.85;">
      <strong>핵심 3줄 브리핑</strong><br>
      1. <b>누구에게</b> : {esc(target_text)}<br>
      2. <b>무엇을</b> : {esc(benefit_text)}<br>
      3. <b>언제까지</b> : {esc(period_text)}
    </div>
    <p style="font-size:16px; line-height:1.9;">{intro_html}</p>
    <br>
    <h3 style="font-size:19px; color:#0f172a;">1) 지원 대상 및 지역 기준</h3>
    <p style="font-size:16px; line-height:1.9;">
      해당 제도는 <strong>{esc(region_label)}</strong> 기준으로 운영되며, 기본 신청 대상은 <strong>{esc(target_text)}</strong>입니다.<br>
      {t_comm}
    </p>
    <hr style="border:0; border-top:1px solid #e2e8f0; margin:22px 0;">
    <h3 style="font-size:19px; color:#0f172a;">2) 세부 지원 내용</h3>
    <p style="font-size:16px; line-height:1.9;">
      요건을 충족할 경우 <strong>{esc(benefit_text)}</strong> 혜택을 받을 수 있습니다.<br>
      {b_comm}
    </p>
    {info_block}
    <h3 style="font-size:19px; color:#0f172a;">3) 접수 기간 및 공식 신청 경로</h3>
    <p style="font-size:16px; line-height:1.9;">
      신청 기간은 <strong>{esc(period_text)}</strong>이며, 주관처({esc(org)}) 공식 사이트를 통해 온라인 확인 및 접수가 진행됩니다.
    </p>
    {link_card}
    <p style="font-size:16px; line-height:1.9;">{closing}</p>
    <br>
    <p style="font-size:14px; color:#64748b;">{esc(hashtag_str)}</p>
"""

    # -------------------- F5: 일정·꿀팁 집중형 (경쾌한 생활정보체)
    intro_html = nl2br(ai_sections["intro"]) if ai_sections else nl2br(_pick_variant(cat_intros_polite.get(blog_cat, cat_intros_polite["돈·지원금"]), vkey + ":t"))
    t_comm = nl2br(ai_sections["target_comment"]) if ai_sections else "처음에는 조건이 까다로워 보여도 온라인 조회 화면에서 본인 인증만 거치면 대상 여부가 금방 나와요."
    b_comm = nl2br(ai_sections["benefit_comment"]) if ai_sections else "신청만 제때 해두면 직접적인 금전·생활 혜택을 챙길 수 있으니 그냥 넘기면 아깝겠죠."
    closing = nl2br(ai_sections["closing"]) if ai_sections else "오늘 정리해 드린 내용이 작은 보탬이 되었길 바라며, 해당되시는 분들은 잊지 말고 꼭 챙겨보세요!"

    return f"""
    {thumb_block}
    <p style="font-size:16px; line-height:1.9;">{intro_html}</p>
    <br>
    <h3 style="font-size:19px; color:#065f46; border-left:5px solid #059669; padding-left:12px;">언제, 어디서 신청할 수 있을까요?</h3>
    <p style="font-size:16px; line-height:1.9;">
      가장 먼저 챙겨야 할 신청 일정은 <strong>{esc(period_text)}</strong>이에요.<br>
      <strong>{esc(org)}</strong>({esc(region_label)})에서 운영하며, 스마트폰이나 PC로 공식 홈페이지에서 바로 접수할 수 있습니다.
    </p>
    {link_card}
    <h3 style="font-size:19px; color:#065f46; border-left:5px solid #059669; padding-left:12px;">내가 받을 수 있는 대상인지 확인하기</h3>
    <p style="font-size:16px; line-height:1.9;">
      지원 대상 기준은 <strong>{esc(target_text)}</strong>으로 정해져 있어요.<br>
      {t_comm}
    </p>
    {info_block}
    <h3 style="font-size:19px; color:#065f46; border-left:5px solid #059669; padding-left:12px;">실제로 받는 혜택과 체크 포인트</h3>
    <p style="font-size:16px; line-height:1.9;">
      핵심 지원 혜택은 <strong>{esc(benefit_text)}</strong>입니다.<br>
      {b_comm}
    </p>
    <p style="font-size:16px; line-height:1.9;">{closing}</p>
    <br>
    <p style="font-size:14px; color:#64748b;">{esc(hashtag_str)}</p>
"""


def cleanup_old_blog_files(
    retention_days: int = 10,
    today: Optional[date] = None,
    blog_dir: Optional[Path] = None,
) -> List[Path]:
    """생성된 지 retention_days(기본 10일) 이상 지난 블로그 원고(.html/.md) 및 이미지(.png) 파일을 자동 삭제"""
    ref_today = today or date.today()
    target_dir = blog_dir if blog_dir is not None else BLOG_DIR
    removed: List[Path] = []
    if not target_dir.exists():
        return removed

    for p in list(target_dir.rglob("*")):
        if not p.is_file():
            continue
        m = re.match(r"^(\d{4}-\d{2}-\d{2})_", p.name)
        if not m:
            continue
        try:
            file_date = date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if (ref_today - file_date).days >= retention_days:
            try:
                p.unlink()
                removed.append(p)
            except OSError:
                pass
    return removed


def build_blog_package_for_today(
    today: Optional[date] = None,
    history_path: Path = BLOG_HISTORY_PATH,
    items_override: Optional[List[Any]] = None,
) -> Optional[Dict[str, Any]]:
    ref_today = today or date.today()
    today_str = ref_today.strftime("%Y-%m-%d")

    cleanup_old_blog_files(retention_days=10, today=ref_today)

    history = load_blog_history(history_path)
    candidates = pick_candidates(
        top_n=10,
        today=ref_today,
        history_path=history_path,
        items_override=items_override,
    )
    if not candidates:
        # 중요: 후보가 없을 때 blog_history.json 을 삭제해 중복 글을 재발송하던 기존 버그 완전 제거!
        print("[INFO] 쿨다운 내 미작성 신규 혜택 후보가 없어 중복 원고 생성을 건너뜁니다.")
        return None

    chosen = candidates[0]
    bid = chosen["id"]
    raw_title = chosen["title"]
    short_name = _clean_short_title(raw_title)
    org = chosen["organization"]
    region_label = chosen["blog_region"]
    target_text = chosen["target_summary"]
    benefit_text = chosen["summary"]
    period_text = chosen["apply_period_text"]
    detail_url = chosen["url"]
    apply_url = chosen.get("apply_url") or detail_url

    blog_cat = map_blog_category(chosen["category"], raw_title)
    amount_highlight = _extract_short_amount(benefit_text)
    format_id, theme_id = _pick_next_rotation(history, ref_today, bid)

    titles = _build_titles(short_name, amount_highlight, blog_cat, period_text, format_id)

    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r"[^a-zA-Z0-9가-힣]+", "-", short_name).strip("-")[:24]
    thumb_path = IMG_DIR / f"{today_str}_{slug}_thumbnail.png"
    info_path = IMG_DIR / f"{today_str}_{slug}_infographic.png"

    # 글자 중간 절단([:14], [:28]) 제거 -> blog_image_generator 내부에서 픽셀 폭 기준 자동 피팅·어절 줄바꿈 처리
    generate_benefit_thumbnail(
        out_path=thumb_path,
        badge_text=f"{blog_cat} · {region_label}",
        title_line1=short_name,
        highlight_line2=amount_highlight,
        sub_title="지원 대상 · 혜택 범위 · 온라인 신청 핵심 정리",
        check_items=[
            f"대상: {target_text}",
            f"혜택: {benefit_text}",
            f"주관: {org}",
        ],
        footer_text=f"신청일정: {period_text}",
        theme_id=theme_id,
    )

    generate_benefit_infographic(
        out_path=info_path,
        header_tag=f"{blog_cat} 핵심 요약표",
        header_title=f"{short_name} 신청 가이드",
        rows=[
            ("01. 지원 대상", target_text, f"적용 지역: {region_label}"),
            ("02. 지원 혜택", benefit_text, "세부 지급 기준은 공식 공고문 참조"),
            ("03. 주관 기관", org, f"카테고리: {blog_cat}"),
            ("04. 신청 일정", period_text, "예산 소진 전 여유 있게 접수 권장"),
            ("05. 신청 방법", "공식 온라인 접수창구 본인인증 신청", apply_url),
        ],
        tip_title="신청 전 챙겨두면 좋은 체크포인트 3가지",
        tip_lines=[
            "본인 연령·거주지·소득 구간이 공고 기준과 일치하는지 먼저 조회",
            "온라인 신청 시 행정정보 공동이용(마이데이터) 동의하면 서류 제출 간소화",
            "선착순·예산 한도 사업은 마감 직전보다 초기에 접수하는 것이 유리",
        ],
        theme_id=theme_id,
    )

    thumb_b64 = _encode_png_base64(thumb_path)
    info_b64 = _encode_png_base64(info_path)

    hashtags = _build_hashtags(short_name, org, blog_cat, region_label)
    hashtag_str = " ".join(hashtags)

    ai_sections = _try_gemini_custom_sections(
        format_id=format_id,
        short_name=short_name,
        org=org,
        region_label=region_label,
        target_text=target_text,
        benefit_text=benefit_text,
        period_text=period_text,
        blog_cat=blog_cat,
    )

    body_inner_html = _render_body_by_format(
        format_id=format_id,
        short_name=short_name,
        raw_title=raw_title,
        org=org,
        region_label=region_label,
        target_text=target_text,
        benefit_text=benefit_text,
        period_text=period_text,
        detail_url=detail_url,
        apply_url=apply_url,
        blog_cat=blog_cat,
        thumb_b64=thumb_b64,
        info_b64=info_b64,
        hashtag_str=hashtag_str,
        today_str=today_str,
        ai_sections=ai_sections,
    )

    esc = lambda s: html.escape(str(s or ""), quote=True)
    format_label = FORMAT_LABELS.get(format_id, format_id)

    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(titles[0])}</title>
<style>
  body {{
    margin: 0;
    padding: 0;
    background: #f1f5f9;
    font-family: 'Pretendard', 'Malgun Gothic', -apple-system, sans-serif;
    color: #1e293b;
  }}
  .toolbar {{
    position: sticky;
    top: 0;
    z-index: 100;
    background: #0f172a;
    color: #ffffff;
    padding: 14px 24px;
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  }}
  .toolbar .btn-group {{
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }}
  .btn {{
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 14px;
    font-weight: 700;
    cursor: pointer;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }}
  .btn-copy {{ background: #22c55e; color: #052e16; }}
  .btn-dl {{ background: #3b82f6; color: #ffffff; }}
  .paper {{
    max-width: 780px;
    margin: 28px auto 60px;
    background: #ffffff;
    border-radius: 16px;
    padding: 36px 40px;
    box-shadow: 0 4px 20px rgba(15, 23, 42, 0.08);
  }}
  .meta-box {{
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 28px;
    font-size: 14px;
    line-height: 1.7;
  }}
</style>
</head>
<body>

<div class="toolbar">
  <div>
    <strong>📝 오늘의 밍팁 혜택 원고 ({esc(today_str)})</strong><br>
    <span style="font-size:13px; color:#cbd5e1;">포맷: <b>{esc(format_label)}</b> · 테마: <b>{esc(theme_id)}</b></span>
  </div>
  <div class="btn-group">
    <a class="btn btn-dl" href="data:image/png;base64,{thumb_b64}" download="{today_str}_{esc(slug)}_01_thumb.png">💾 썸네일 저장</a>
    <a class="btn btn-dl" href="data:image/png;base64,{info_b64}" download="{today_str}_{esc(slug)}_02_summary.png">💾 요약표 저장</a>
    <button class="btn btn-copy" onclick="copyBlogContent()">📋 본문 서식 통째로 복사</button>
  </div>
</div>

<div class="paper">
  <div class="meta-box">
    <div style="margin-bottom:12px; padding-bottom:10px; border-bottom:1px solid #cbd5e1;">
      <strong>📂 발행 카테고리 :</strong>
      <span style="background:#2563eb; color:#fff; padding:4px 10px; border-radius:6px; font-weight:bold; font-size:14px; margin-left:6px;">{esc(blog_cat)}</span>
      <span style="font-size:13px; color:#64748b; margin-left:8px;">(mingtip 탭: 돈·지원금 / 건강·접종 / 살림·생활 / 폰·행정)</span>
    </div>
    <strong>💡 추천 제목 3선 (1번 제목이 오늘의 포맷과 가장 잘 맞습니다)</strong>
    <ol style="margin:8px 0 0 0; padding-left:20px;">
      <li><b>{esc(titles[0])}</b></li>
      <li><b>{esc(titles[1])}</b></li>
      <li><b>{esc(titles[2])}</b></li>
    </ol>
  </div>

  <div id="blog-body">
{body_inner_html}
  </div>
</div>

<script>
function copyBlogContent() {{
  const node = document.getElementById('blog-body');
  const range = document.createRange();
  range.selectNodeContents(node);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  try {{
    document.execCommand('copy');
    alert('✅ 본문 서식이 복사되었습니다! 네이버 스마트에디터 본문에 Ctrl+V로 붙여넣으세요.');
  }} catch (err) {{
    alert('복사 실패: 본문 영역을 마우스로 드래그해 Ctrl+C 해주세요.');
  }}
  sel.removeAllRanges();
}}
</script>

</body>
</html>
"""

    html_path = BLOG_DIR / f"{today_str}_{slug}.html"
    html_path.write_text(html_content, encoding="utf-8")

    save_blog_history(
        bid,
        raw_title,
        f"blog_posts/{html_path.name}",
        format_id=format_id,
        theme_id=theme_id,
        blog_category=blog_cat,
        ref_date=ref_today,
        path=history_path,
    )

    return {
        "id": bid,
        "title": raw_title,
        "recommended_title": titles[0],
        "titles": titles,
        "blog_category": blog_cat,
        "format_id": format_id,
        "format_label": format_label,
        "theme_id": theme_id,
        "thumb_path": thumb_path,
        "info_path": info_path,
        "html_path": html_path,
    }


if __name__ == "__main__":
    pkg = build_blog_package_for_today()
    if pkg:
        print(
            f"[OK] 블로그 패키지 생성 완료:\n"
            f" - 카테고리: {pkg['blog_category']} | 포맷: {pkg['format_id']} | 테마: {pkg['theme_id']}\n"
            f" - 추천제목: {pkg['recommended_title']}\n"
            f" - HTML: {pkg['html_path']}\n"
            f" - 썸네일: {pkg['thumb_path']}\n"
            f" - 요약표: {pkg['info_path']}"
        )
    else:
        print("[SKIP] 신규 후보 없음 (중복 발송 차단됨)")
