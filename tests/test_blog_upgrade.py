from datetime import date, timedelta
from pathlib import Path
import re
from PIL import Image

from src.blog_image_generator import THEME_ORDER, generate_benefit_infographic, generate_benefit_thumbnail
from src.blog_picker import load_blog_history, normalize_benefit_key, pick_candidates, save_blog_history
from src.daily_blog_generator import FORMAT_ORDER, build_blog_package_for_today, map_blog_category
from src.models import BenefitItem


def test_normalize_benefit_key_blocks_cross_source_duplicates(tmp_path: Path):
    hist = tmp_path / "blog_history.json"
    save_blog_history(
        "seed_lllcard",
        "평생교육이용권 (평생교육바우처)",
        "blog_posts/old.html",
        ref_date=date(2026, 11, 20),
        path=hist,
    )

    items = [
        BenefitItem(
            id="lllcard_gyeonggi_2026_new",
            title="[경기] 2026 평생교육이용권 추가 신청 접수 (우수이용자)",
            category="교육·바우처",
            organization="국가평생교육진흥원",
            target_summary="만 19세 이상 성인",
            summary="수강료 35만 원 포인트 지원",
            apply_period_text="2026.11.01 ~ 2026.12.10",
            region="경기",
        ),
        BenefitItem(
            id="wevity_999",
            title="국회의원 청년명예보좌관 2기 모집",
            category="대외활동",
            organization="국회",
            target_summary="청년 누구나",
            summary="수료증 지급",
            apply_period_text="상시",
            region="전국",
        ),
        BenefitItem(
            id="seed_energy_voucher",
            title="에너지바우처 (난방비 지원)",
            category="살림·생활",
            organization="한국에너지공단",
            target_summary="수급가구 중 노인·영유아 포함 세대",
            summary="동절기 전기·도시가스 요금 바우처 지원",
            apply_period_text="2026.05.29 ~ 2026.12.31",
            region="전국",
        ),
    ]

    cands = pick_candidates(
        top_n=5,
        today=date(2026, 11, 27),
        history_path=hist,
        items_override=items,
    )
    assert [c["id"] for c in cands] == ["seed_energy_voucher"]
    assert normalize_benefit_key("[경기] 2026 평생교육이용권 신청") == "평생교육이용권"


def test_exhausted_candidates_never_delete_history(tmp_path: Path, monkeypatch):
    import src.daily_blog_generator as dbg

    monkeypatch.setattr(dbg, "BLOG_DIR", tmp_path / "blog_posts")
    monkeypatch.setattr(dbg, "IMG_DIR", tmp_path / "blog_posts" / "images")
    hist = tmp_path / "blog_history.json"

    only_item = [
        BenefitItem(
            id="seed_only_one",
            title="선택약정 25% 통신비 요금할인",
            category="폰·행정",
            organization="스마트초이스",
            target_summary="자급제·약정만료 스마트폰 이용자",
            summary="매월 통신요금 25% 할인",
            apply_period_text="연중 상시",
            region="전국",
        )
    ]

    pkg1 = build_blog_package_for_today(today=date(2026, 11, 27), history_path=hist, items_override=only_item)
    assert pkg1 is not None
    assert pkg1["blog_category"] == "폰·행정"
    assert len(load_blog_history(hist)) == 1

    # 다음 날 같은 후보만 남았을 때 히스토리를 삭제하지 않고 None 반환(중복 발송 원천 차단)
    pkg2 = build_blog_package_for_today(today=date(2026, 11, 28), history_path=hist, items_override=only_item)
    assert pkg2 is None
    assert hist.exists()
    assert len(load_blog_history(hist)) == 1


def test_five_formats_and_themes_rotate_without_consecutive_repeats(tmp_path: Path, monkeypatch):
    import src.daily_blog_generator as dbg

    monkeypatch.setattr(dbg, "BLOG_DIR", tmp_path / "blog_posts")
    monkeypatch.setattr(dbg, "IMG_DIR", tmp_path / "blog_posts" / "images")
    hist = tmp_path / "blog_history.json"

    items = [
        BenefitItem(
            id=f"seed_item_{i}",
            title=title,
            category=cat,
            organization="주관기관",
            target_summary="만 19세 이상 해당 요건 충족 국민 누구나 신청 가능",
            summary=f"연 최대 {i * 10}만 원 지원 및 수수료 감면 혜택 제공",
            apply_period_text="2026.01.01 ~ 2026.12.31 (예산 소진 시 마감)",
            region="전국",
        )
        for i, (title, cat) in enumerate(
            [
                ("국가건강검진 무료 대상 조회", "건강·접종"),
                ("통신 미환급금 통합 조회", "폰·행정"),
                ("탄소중립포인트 에너지 인센티브", "살림·생활"),
                ("근로장려금 정기 신청", "돈·지원금"),
                ("국민취업지원제도 구직촉진수당", "돈·지원금"),
            ],
            start=1,
        )
    ]

    formats = []
    themes = []
    bodies = []
    base_day = date(2026, 11, 28)

    for offset in range(5):
        pkg = build_blog_package_for_today(
            today=base_day + timedelta(days=offset),
            history_path=hist,
            items_override=items,
        )
        assert pkg is not None
        assert pkg["format_id"] in FORMAT_ORDER
        assert pkg["theme_id"] in THEME_ORDER
        formats.append(pkg["format_id"])
        themes.append(pkg["theme_id"])

        html_txt = pkg["html_path"].read_text(encoding="utf-8")
        # 옛 고정 상투구("요즘 물가도 오르고 고정 지출이 늘어나면서") 미포함 검증
        assert "요즘 물가도 오르고 고정 지출이 늘어나면서" not in html_txt
        bodies.append(re.sub(r"<[^>]+>", " ", html_txt))

        with Image.open(pkg["thumb_path"]) as im_t:
            assert im_t.size == (900, 900)
        with Image.open(pkg["info_path"]) as im_i:
            assert im_i.size[0] == 900

    # 연속된 두 날짜에 동일한 포맷이나 동일한 테마가 나오지 않아야 함
    for idx in range(1, len(formats)):
        assert formats[idx] != formats[idx - 1]
        assert themes[idx] != themes[idx - 1]


def test_map_blog_category_matches_live_mingtip_tabs():
    assert map_blog_category("건강·접종", "인플루엔자 국가예방접종") == "건강·접종"
    assert map_blog_category("폰·행정", "선택약정 25% 통신비 할인") == "폰·행정"
    assert map_blog_category("살림·생활", "에너지바우처 난방비") == "살림·생활"
    assert map_blog_category("청년·적금", "청년도약계좌") == "돈·지원금"
