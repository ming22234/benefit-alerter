from pathlib import Path
from typing import List, Tuple
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent.parent
FONT_DISPLAY = str(BASE_DIR / "assets" / "fonts" / "BlackHanSans-Regular.ttf")
FONT_BOLD_CANDIDATES = [
    "C:/Windows/Fonts/malgunbd.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    FONT_DISPLAY,
]
FONT_REG_CANDIDATES = [
    "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    FONT_DISPLAY,
]
FONT_BOLD = FONT_BOLD_CANDIDATES[0]
FONT_REG = FONT_REG_CANDIDATES[0]


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    candidates = [path]
    if path == FONT_BOLD:
        candidates = FONT_BOLD_CANDIDATES
    elif path == FONT_REG:
        candidates = FONT_REG_CANDIDATES
    else:
        candidates = [path] + FONT_BOLD_CANDIDATES

    for cand in candidates:
        if Path(cand).exists():
            try:
                return ImageFont.truetype(cand, size)
            except Exception:
                continue
    return ImageFont.load_default()


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


def _draw_checkmark(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: int = 18, bg=(37, 99, 235)) -> None:
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=bg)
    # 벡터 체크마크 그리기 (폰트 깨짐 원천 방지)
    p1 = (cx - 8, cy + 1)
    p2 = (cx - 2, cy + 7)
    p3 = (cx + 9, cy - 6)
    draw.line([p1, p2, p3], fill=(255, 255, 255), width=4, joint="curve")


def generate_benefit_thumbnail(
    out_path: Path,
    badge_text: str,
    title_line1: str,
    highlight_line2: str,
    sub_title: str,
    check_items: List[str],
    footer_text: str,
) -> Path:
    """네이버 블로그 대표 사진용 900x900 고해상도 정사각형 썸네일 생성"""
    W, H = 900, 900
    img = _draw_vertical_gradient(W, H, (15, 29, 64), (29, 78, 216))
    draw = ImageDraw.Draw(img)

    # 배경 장식 원형 패턴
    draw.ellipse([620, -120, 1020, 280], fill=(37, 99, 235))
    draw.ellipse([-140, 640, 260, 1040], fill=(23, 55, 130))

    # 메인 카드 프레임
    card_box = [48, 48, W - 48, H - 48]
    draw.rounded_rectangle(card_box, radius=36, fill=(17, 34, 77), outline=(96, 165, 250), width=3)

    f_badge = _load_font(FONT_BOLD, 27)
    f_title = _load_font(FONT_DISPLAY, 66)
    f_high = _load_font(FONT_DISPLAY, 74)
    f_sub = _load_font(FONT_BOLD, 33)
    f_check = _load_font(FONT_BOLD, 27)
    f_foot = _load_font(FONT_BOLD, 27)

    # 1. 상단 뱃지
    badge_w = draw.textlength(badge_text, font=f_badge) + 56
    bx1 = (W - badge_w) / 2
    draw.rounded_rectangle([bx1, 102, bx1 + badge_w, 162], radius=30, fill=(250, 204, 21))
    draw.text((W / 2, 132), badge_text, font=f_badge, fill=(15, 23, 42), anchor="mm")

    # 2. 메인 타이틀 1줄 & 강조 2줄
    draw.text((W / 2, 238), title_line1, font=f_title, fill=(255, 255, 255), anchor="mm")

    hw = draw.textlength(highlight_line2, font=f_high) + 56
    hx1 = (W - hw) / 2
    draw.rounded_rectangle([hx1, 294, hx1 + hw, 394], radius=18, fill=(16, 185, 129))
    draw.text((W / 2, 346), highlight_line2, font=f_high, fill=(255, 255, 255), anchor="mm")

    # 3. 부제목
    draw.text((W / 2, 446), sub_title, font=f_sub, fill=(191, 219, 254), anchor="mm")

    # 4. 화이트 체크리스트 박스 (여백 넉넉하게 확보)
    draw.rounded_rectangle([82, 496, W - 82, 736], radius=24, fill=(255, 255, 255))
    y_cursor = 548
    for item in check_items[:3]:
        _draw_checkmark(draw, 134, y_cursor, r=18, bg=(37, 99, 235))
        draw.text((168, y_cursor), item, font=f_check, fill=(30, 41, 59), anchor="lm")
        y_cursor += 68

    # 5. 하단 안내 바
    draw.text((W / 2, 792), footer_text, font=f_foot, fill=(253, 224, 71), anchor="mm")

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
) -> Path:
    """본문 삽입용 900x1160 핵심 요약 & 신청 체크리스트 인포그래픽 생성"""
    W, H = 900, 1160
    img = Image.new("RGB", (W, H), (241, 245, 249))
    draw = ImageDraw.Draw(img)

    # 상단 헤더 영역
    draw.rounded_rectangle([36, 36, W - 36, 206], radius=28, fill=(30, 58, 138))
    f_tag = _load_font(FONT_BOLD, 23)
    f_head = _load_font(FONT_DISPLAY, 41)
    f_lbl = _load_font(FONT_BOLD, 25)
    f_val_main = _load_font(FONT_BOLD, 27)
    f_val_sub = _load_font(FONT_REG, 21)
    f_tip_t = _load_font(FONT_BOLD, 26)
    f_tip_b = _load_font(FONT_BOLD, 21)

    tag_w = draw.textlength(header_tag, font=f_tag) + 40
    draw.rounded_rectangle([68, 60, 68 + tag_w, 102], radius=20, fill=(59, 130, 246))
    draw.text((68 + tag_w / 2, 81), header_tag, font=f_tag, fill=(255, 255, 255), anchor="mm")
    draw.text((68, 150), header_title, font=f_head, fill=(255, 255, 255), anchor="lm")

    # 5개 핵심 항목 카드
    y_top = 230
    card_h = 122
    accent_colors = [
        (37, 99, 235),
        (16, 185, 129),
        (124, 58, 237),
        (234, 88, 12),
        (220, 38, 38),
    ]

    for idx, (label, main_txt, sub_txt) in enumerate(rows[:5]):
        color = accent_colors[idx % len(accent_colors)]
        draw.rounded_rectangle([36, y_top, W - 36, y_top + card_h], radius=20, fill=(255, 255, 255), outline=(203, 213, 225), width=2)
        # 좌측 컬러 탭
        draw.rounded_rectangle([36, y_top, 244, y_top + card_h], radius=20, fill=color)
        draw.rectangle([224, y_top, 244, y_top + card_h], fill=color)
        draw.text((140, y_top + card_h / 2), label, font=f_lbl, fill=(255, 255, 255), anchor="mm")

        # 우측 본문
        draw.text((268, y_top + 40), main_txt, font=f_val_main, fill=(15, 23, 42), anchor="lm")
        draw.text((268, y_top + 84), sub_txt, font=f_val_sub, fill=(71, 85, 105), anchor="lm")
        y_top += card_h + 15

    # 하단 필수 서류 / 주의사항 박스
    draw.rounded_rectangle([36, y_top + 6, W - 36, H - 36], radius=22, fill=(254, 249, 195), outline=(250, 204, 21), width=3)
    draw.rounded_rectangle([64, y_top + 24, 154, y_top + 60], radius=10, fill=(202, 138, 4))
    draw.text((109, y_top + 42), "필수체크", font=_load_font(FONT_BOLD, 20), fill=(255, 255, 255), anchor="mm")
    draw.text((168, y_top + 42), tip_title, font=f_tip_t, fill=(133, 77, 14), anchor="lm")

    ty = y_top + 88
    for t_line in tip_lines[:3]:
        draw.text((68, ty), f"• {t_line}", font=f_tip_b, fill=(66, 32, 6), anchor="lm")
        ty += 38

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path


if __name__ == "__main__":
    base_img_dir = Path(__file__).resolve().parent.parent / "blog_posts" / "images"

    thumb_file = base_img_dir / "2026-10-27_thumbnail.png"
    info_file = base_img_dir / "2026-10-27_infographic.png"

    generate_benefit_thumbnail(
        out_path=thumb_file,
        badge_text="2026 하반기 마감 임박 · 소득 제한 없음",
        title_line1="토익 + 자격증 시험비",
        highlight_line2="최대 30만원 현금 환급",
        sub_title="경기청년 역량강화 기회지원 신청 가이드",
        check_items=[
            "대상: 만 19~39세 미취업 청년 (단기알바 가능)",
            "분야: 토익·오픽·한국사·컴활·자격증 1,005종",
            "혜택: 응시료 및 수강료 연 30만원 계좌 입금",
        ],
        footer_text="[신청기한] ~11월 30일 (예산 소진 시 선착순 마감)",
    )

    generate_benefit_infographic(
        out_path=info_file,
        header_tag="한눈에 보는 신청 요약표",
        header_title="2026 경기청년 역량강화 기회지원 핵심 정리",
        rows=[
            ("01. 지원 대상", "만 19세 ~ 39세 미취업 청년", "경기도 거주자 · 부모/본인 소득 및 자산 제한 없음"),
            ("02. 미취업 기준", "시험 응시일 당시 미취업이면 신청 가능!", "현재 취업했어도 응시 때 미취업이면 OK (단기알바 포함)"),
            ("03. 지원 금액", "1인당 연 최대 30만 원 실비 현금 환급", "실제 결제한 시험 응시료 및 학원 수강료 본인 계좌 입금"),
            ("04. 지원 시험", "어학 19종 + 한국사 + 국가·공인자격 1,005종", "토익, 오픽, 토스, 컴활, 정보처리기사, 공인중개사, ADsP 등"),
            ("05. 신청 방법", "잡아바 어플라이 (apply.jobaba.net)", "공공 마이데이터 연동 시 초본·건강보험자격득실 자동 제출"),
        ],
        tip_title="신청 전 미리 준비할 필수 첨부파일 3가지",
        tip_lines=[
            "① 응시확인서 또는 성적표 (단순 수험표는 응시 확인 불가로 반려 주의)",
            "② 결제 영수증 (카드전표·현금영수증·이체확인증 / 문자 캡처 불가)",
            "③ 지원금 입금받을 본인 명의 통장 사본 (모바일 통장사본 가능)",
        ],
    )
    print(f"[OK] Generated:\n - {thumb_file}\n - {info_file}")
