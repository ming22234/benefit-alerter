from pathlib import Path
from typing import Dict, List, Tuple
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent.parent
FONT_DISPLAY = str(BASE_DIR / "assets" / "fonts" / "BlackHanSans-Regular.ttf")
FONT_BOLD_CANDIDATES = [
    "C:/Windows/Fonts/NotoSansKR-Bold.otf",
    "C:/Windows/Fonts/malgunbd.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    FONT_DISPLAY,
]
FONT_REG_CANDIDATES = [
    "C:/Windows/Fonts/NotoSansKR-Medium.otf",
    "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/nanum/NanumSquareR.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    FONT_DISPLAY,
]
FONT_BOLD = FONT_BOLD_CANDIDATES[0]
FONT_REG = FONT_REG_CANDIDATES[0]

# 4종 순환 비주얼 테마 (다크 2종 + 라이트 매거진 2종 교차 배치로 공장형 획일화 방지)
THEMES: Dict[str, Dict[str, Tuple[int, int, int]]] = {
    "navy_editorial": {
        "bg_top": (15, 29, 64),
        "bg_bot": (28, 68, 178),
        "deco1": (37, 99, 235),
        "deco2": (20, 48, 118),
        "card_bg": (18, 36, 82),
        "card_border": (96, 165, 250),
        "badge_bg": (250, 204, 21),
        "badge_fg": (15, 23, 42),
        "title_fg": (255, 255, 255),
        "pill_bg": (16, 185, 129),
        "pill_fg": (255, 255, 255),
        "sub_fg": (191, 219, 254),
        "box_bg": (255, 255, 255),
        "box_fg": (30, 41, 59),
        "check_bg": (37, 99, 235),
        "foot_fg": (253, 224, 71),
        "info_head": (24, 49, 114),
        "info_tag": (59, 130, 246),
    },
    "warm_cream": {
        "bg_top": (251, 247, 239),
        "bg_bot": (242, 234, 220),
        "deco1": (245, 224, 198),
        "deco2": (236, 218, 196),
        "card_bg": (255, 253, 249),
        "card_border": (218, 198, 174),
        "badge_bg": (46, 38, 32),
        "badge_fg": (255, 248, 235),
        "title_fg": (34, 28, 24),
        "pill_bg": (224, 79, 56),
        "pill_fg": (255, 255, 255),
        "sub_fg": (108, 88, 72),
        "box_bg": (247, 241, 232),
        "box_fg": (42, 34, 28),
        "check_bg": (224, 79, 56),
        "foot_fg": (168, 62, 42),
        "info_head": (58, 44, 36),
        "info_tag": (224, 79, 56),
    },
    "forest_mint": {
        "bg_top": (16, 52, 44),
        "bg_bot": (24, 84, 68),
        "deco1": (32, 112, 88),
        "deco2": (14, 42, 35),
        "card_bg": (20, 62, 52),
        "card_border": (82, 183, 146),
        "badge_bg": (246, 208, 112),
        "badge_fg": (20, 42, 34),
        "title_fg": (255, 255, 255),
        "pill_bg": (217, 119, 36),
        "pill_fg": (255, 255, 255),
        "sub_fg": (187, 240, 218),
        "box_bg": (248, 253, 250),
        "box_fg": (22, 48, 38),
        "check_bg": (22, 132, 98),
        "foot_fg": (250, 224, 144),
        "info_head": (20, 66, 54),
        "info_tag": (22, 148, 108),
    },
    "slate_royal": {
        "bg_top": (239, 244, 252),
        "bg_bot": (226, 235, 248),
        "deco1": (210, 225, 248),
        "deco2": (218, 230, 246),
        "card_bg": (255, 255, 255),
        "card_border": (191, 209, 236),
        "badge_bg": (37, 99, 235),
        "badge_fg": (255, 255, 255),
        "title_fg": (18, 28, 48),
        "pill_bg": (24, 44, 86),
        "pill_fg": (255, 255, 255),
        "sub_fg": (78, 96, 126),
        "box_bg": (243, 247, 253),
        "box_fg": (28, 40, 64),
        "check_bg": (37, 99, 235),
        "foot_fg": (30, 74, 188),
        "info_head": (26, 44, 82),
        "info_tag": (37, 99, 235),
    },
}

THEME_ORDER = ("navy_editorial", "warm_cream", "forest_mint", "slate_royal")


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    if path == FONT_BOLD:
        candidates = FONT_BOLD_CANDIDATES
    elif path == FONT_REG:
        candidates = FONT_REG_CANDIDATES
    else:
        candidates = [path] + FONT_BOLD_CANDIDATES

    for cand in candidates:
        if Path(cand).exists():
            try:
                return ImageFont.truetype(cand, int(size))
            except Exception:
                continue
    return ImageFont.load_default()


def _fit_single_line(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_key: str,
    max_width: float,
    start_size: int,
    min_size: int = 19,
) -> Tuple[ImageFont.FreeTypeFont, str]:
    """픽셀 폭을 재며 폰트 크기를 자동 조절하고, 그래도 넘치면 어절 단위로 깔끔하게 줄인다(음절 중간 절단 방지)."""
    clean = " ".join(str(text or "").split())
    sz = int(start_size)
    while sz >= min_size:
        fnt = _load_font(font_key, sz)
        if draw.textlength(clean, font=fnt) <= max_width:
            return fnt, clean
        sz -= 2

    fnt = _load_font(font_key, min_size)
    if draw.textlength(clean, font=fnt) <= max_width:
        return fnt, clean

    # 어절 경계 우선 축약
    words = clean.split(" ")
    while len(words) > 1:
        words.pop()
        cand = " ".join(words).rstrip("·,/-:") + "…"
        if draw.textlength(cand, font=fnt) <= max_width:
            return fnt, cand

    cur = clean
    while len(cur) > 2 and draw.textlength(cur + "…", font=fnt) > max_width:
        cur = cur[:-1]
    return fnt, (cur.rstrip() + "…")


def _wrap_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    fnt: ImageFont.FreeTypeFont,
    max_width: float,
    max_lines: int = 2,
) -> List[str]:
    """어절 경계를 우선해 max_lines 줄로 자연스럽게 줄바꿈한다."""
    clean = " ".join(str(text or "").split())
    if not clean:
        return [""]
    if draw.textlength(clean, font=fnt) <= max_width:
        return [clean]

    words = clean.split(" ")
    lines: List[str] = []
    cur = ""
    for w in words:
        cand = f"{cur} {w}".strip() if cur else w
        if draw.textlength(cand, font=fnt) <= max_width:
            cur = cand
        else:
            if cur:
                lines.append(cur)
                cur = w
            else:
                # URL 등 공백 없는 긴 문자열 분할
                chunk = ""
                for ch in w:
                    if draw.textlength(chunk + ch, font=fnt) <= max_width:
                        chunk += ch
                    else:
                        lines.append(chunk)
                        chunk = ch
                cur = chunk
    if cur:
        lines.append(cur)

    if len(lines) <= max_lines:
        return lines

    kept = lines[:max_lines]
    last = kept[-1]
    while len(last) > 2 and draw.textlength(last + "…", font=fnt) > max_width:
        last = last[:-1]
    kept[-1] = last.rstrip(" ·,/-:") + "…"
    return kept


def _draw_vertical_gradient(
    width: int, height: int, top_rgb: Tuple[int, int, int], bottom_rgb: Tuple[int, int, int]
) -> Image.Image:
    base = Image.new("RGB", (width, height), top_rgb)
    draw = ImageDraw.Draw(base)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        r = int(top_rgb[0] + (bottom_rgb[0] - top_rgb[0]) * ratio)
        g = int(top_rgb[1] + (bottom_rgb[1] - top_rgb[1]) * ratio)
        b = int(top_rgb[2] + (bottom_rgb[2] - top_rgb[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    return base


def _draw_checkmark(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: int = 17, bg=(37, 99, 235)) -> None:
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=bg)
    p1 = (cx - 7, cy + 1)
    p2 = (cx - 2, cy + 6)
    p3 = (cx + 8, cy - 5)
    draw.line([p1, p2, p3], fill=(255, 255, 255), width=4, joint="curve")


def generate_benefit_thumbnail(
    out_path: Path,
    badge_text: str,
    title_line1: str,
    highlight_line2: str,
    sub_title: str,
    check_items: List[str],
    footer_text: str,
    theme_id: str = "navy_editorial",
) -> Path:
    """네이버 블로그 대표 사진용 900x900 고해상도 정사각형 썸네일 생성 (글자 잘림 0% · 4종 테마 순환)"""
    theme = THEMES.get(theme_id, THEMES["navy_editorial"])
    W, H = 900, 900
    img = _draw_vertical_gradient(W, H, theme["bg_top"], theme["bg_bot"])
    draw = ImageDraw.Draw(img)

    # 배경 장식 원형 패턴
    draw.ellipse([630, -120, 1020, 270], fill=theme["deco1"])
    draw.ellipse([-140, 650, 250, 1040], fill=theme["deco2"])

    # 메인 카드 프레임
    card_box = [44, 44, W - 44, H - 44]
    draw.rounded_rectangle(card_box, radius=36, fill=theme["card_bg"], outline=theme["card_border"], width=3)

    inner_max_w = W - 160

    # 1. 상단 뱃지
    f_badge, safe_badge = _fit_single_line(draw, badge_text, FONT_BOLD, inner_max_w - 60, 26, min_size=20)
    badge_w = draw.textlength(safe_badge, font=f_badge) + 54
    bx1 = (W - badge_w) / 2
    draw.rounded_rectangle([bx1, 96, bx1 + badge_w, 154], radius=29, fill=theme["badge_bg"])
    draw.text((W / 2, 125), safe_badge, font=f_badge, fill=theme["badge_fg"], anchor="mm")

    # 2. 메인 타이틀 1줄 & 강조 필 배지 2줄 (길이에 맞춰 자동 폰트 축소)
    f_title, safe_title = _fit_single_line(draw, title_line1, FONT_BOLD, inner_max_w, 60, min_size=34)
    draw.text((W / 2, 228), safe_title, font=f_title, fill=theme["title_fg"], anchor="mm")

    f_high, safe_high = _fit_single_line(draw, highlight_line2, FONT_BOLD, inner_max_w - 64, 62, min_size=34)
    hw = draw.textlength(safe_high, font=f_high) + 64
    hx1 = (W - hw) / 2
    draw.rounded_rectangle([hx1, 290, hx1 + hw, 388], radius=22, fill=theme["pill_bg"])
    draw.text((W / 2, 339), safe_high, font=f_high, fill=theme["pill_fg"], anchor="mm")

    # 3. 부제목
    f_sub, safe_sub = _fit_single_line(draw, sub_title, FONT_BOLD, inner_max_w, 30, min_size=21)
    draw.text((W / 2, 438), safe_sub, font=f_sub, fill=theme["sub_fg"], anchor="mm")

    # 4. 체크리스트 박스 (최대 3개 항목, 폭 자동 피팅)
    draw.rounded_rectangle([78, 486, W - 78, 744], radius=24, fill=theme["box_bg"])
    y_cursor = 540
    check_max_w = (W - 78) - 168 - 28
    for item in check_items[:3]:
        _draw_checkmark(draw, 128, y_cursor, r=16, bg=theme["check_bg"])
        f_chk, safe_item = _fit_single_line(draw, item, FONT_BOLD, check_max_w, 25, min_size=18)
        draw.text((162, y_cursor), safe_item, font=f_chk, fill=theme["box_fg"], anchor="lm")
        y_cursor += 76

    # 5. 하단 안내 바
    f_foot, safe_foot = _fit_single_line(draw, footer_text, FONT_BOLD, inner_max_w, 25, min_size=18)
    draw.text((W / 2, 798), safe_foot, font=f_foot, fill=theme["foot_fg"], anchor="mm")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path


def generate_benefit_infographic(
    out_path: Path,
    header_tag: str,
    header_title: str,
    rows: List[Tuple[str, str, str]],
    tip_title: str,
    tip_lines: List[str],
    theme_id: str = "navy_editorial",
) -> Path:
    """본문 삽입용 핵심 요약 & 신청 체크리스트 인포그래픽 생성 (어절 단위 자동 줄바꿈, 잘림 0%)"""
    theme = THEMES.get(theme_id, THEMES["navy_editorial"])
    W = 900
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    f_lbl = _load_font(FONT_BOLD, 24)
    f_val_main = _load_font(FONT_BOLD, 24)
    f_val_sub = _load_font(FONT_REG, 19)
    f_tip_b = _load_font(FONT_BOLD, 20)

    val_max_w = (W - 36) - 266 - 26
    prepared_rows = []
    for label, main_txt, sub_txt in rows[:5]:
        m_lines = _wrap_lines(probe, main_txt, f_val_main, val_max_w, max_lines=2)
        s_lines = _wrap_lines(probe, sub_txt, f_val_sub, val_max_w, max_lines=2) if sub_txt else []
        ch = max(118, 28 + len(m_lines) * 32 + (len(s_lines) * 26 + 6 if s_lines else 0) + 20)
        prepared_rows.append((label, m_lines, s_lines, ch))

    tip_max_w = (W - 36) - 68 - 28
    wrapped_tips: List[str] = []
    for t_line in tip_lines[:3]:
        t_wrapped = _wrap_lines(probe, f"• {t_line}", f_tip_b, tip_max_w, max_lines=2)
        wrapped_tips.extend(t_wrapped)

    rows_total_h = sum(r[3] for r in prepared_rows) + max(0, len(prepared_rows) - 1) * 14
    tip_box_h = 84 + len(wrapped_tips) * 34 + 24
    H = 228 + rows_total_h + 20 + tip_box_h + 38

    img = Image.new("RGB", (W, H), (242, 245, 250))
    draw = ImageDraw.Draw(img)

    # 상단 헤더 영역
    draw.rounded_rectangle([36, 34, W - 36, 204], radius=28, fill=theme["info_head"])
    f_tag, safe_tag = _fit_single_line(draw, header_tag, FONT_BOLD, W - 180, 22, min_size=18)
    tag_w = draw.textlength(safe_tag, font=f_tag) + 40
    draw.rounded_rectangle([68, 58, 68 + tag_w, 100], radius=20, fill=theme["info_tag"])
    draw.text((68 + tag_w / 2, 79), safe_tag, font=f_tag, fill=(255, 255, 255), anchor="mm")

    f_head, safe_head = _fit_single_line(draw, header_title, FONT_BOLD, W - 140, 38, min_size=24)
    draw.text((68, 148), safe_head, font=f_head, fill=(255, 255, 255), anchor="lm")

    # 5개 핵심 항목 카드
    y_top = 226
    accent_colors = [
        (37, 99, 235),
        (16, 185, 129),
        (124, 58, 237),
        (217, 119, 36),
        (220, 58, 58),
    ]

    for idx, (label, m_lines, s_lines, card_h) in enumerate(prepared_rows):
        color = accent_colors[idx % len(accent_colors)]
        draw.rounded_rectangle(
            [36, y_top, W - 36, y_top + card_h],
            radius=20,
            fill=(255, 255, 255),
            outline=(206, 216, 228),
            width=2,
        )
        draw.rounded_rectangle([36, y_top, 240, y_top + card_h], radius=20, fill=color)
        draw.rectangle([220, y_top, 240, y_top + card_h], fill=color)
        f_l, safe_lbl = _fit_single_line(draw, label, FONT_BOLD, 182, 23, min_size=18)
        draw.text((138, y_top + card_h / 2), safe_lbl, font=f_l, fill=(255, 255, 255), anchor="mm")

        total_text_h = len(m_lines) * 31 + (len(s_lines) * 25 + 6 if s_lines else 0)
        vy = y_top + (card_h - total_text_h) // 2 + 12
        for ml in m_lines:
            draw.text((266, vy), ml, font=f_val_main, fill=(15, 23, 42), anchor="lm")
            vy += 31
        if s_lines:
            vy += 6
            for sl in s_lines:
                draw.text((266, vy), sl, font=f_val_sub, fill=(71, 85, 105), anchor="lm")
                vy += 25

        y_top += card_h + 14

    # 하단 필수 서류 / 주의사항 박스
    tip_y1 = y_top + 6
    tip_y2 = tip_y1 + tip_box_h
    draw.rounded_rectangle(
        [36, tip_y1, W - 36, tip_y2],
        radius=22,
        fill=(254, 250, 224),
        outline=(234, 179, 8),
        width=2,
    )
    draw.rounded_rectangle([64, tip_y1 + 22, 158, tip_y1 + 58], radius=10, fill=(202, 138, 4))
    draw.text((111, tip_y1 + 40), "필수체크", font=_load_font(FONT_BOLD, 19), fill=(255, 255, 255), anchor="mm")
    f_tip_t, safe_tip_t = _fit_single_line(draw, tip_title, FONT_BOLD, W - 230, 24, min_size=18)
    draw.text((172, tip_y1 + 40), safe_tip_t, font=f_tip_t, fill=(120, 68, 12), anchor="lm")

    ty = tip_y1 + 84
    for tl in wrapped_tips:
        draw.text((68, ty), tl, font=f_tip_b, fill=(66, 32, 6), anchor="lm")
        ty += 34

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path
