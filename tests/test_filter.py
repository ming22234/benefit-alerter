from datetime import date
from src.models import BenefitItem
from src.config_loader import calculate_age
from src.filter import deduplicate_similar_items, filter_and_classify_benefits


def test_deduplicate_similar_items():
    items = [
        BenefitItem(
            id="n1",
            title="청년미래적금 2차 신청 68.8만···11월16일 계좌개설 시작",
            category="청년/금융",
            organization="뉴스1",
            summary="요약",
            apply_period_text="상시",
        ),
        BenefitItem(
            id="n2",
            title="청년미래적금 2차 신청자 68만8000명…11월 16일부터 계좌 개설",
            category="청년/금융",
            organization="뉴스2",
            summary="요약",
            apply_period_text="상시",
        ),
        BenefitItem(
            id="n3",
            title="베일 벗은 ‘청년미래적금’…청년층 관심 속 신청 시작",
            category="청년/금융",
            organization="뉴스3",
            summary="요약",
            apply_period_text="상시",
        ),
    ]
    deduped = deduplicate_similar_items(items)
    assert len(deduped) == 1
    assert deduped[0].id == "n1"


def test_calculate_age():
    assert calculate_age(1995, reference_date=date(2026, 10, 26)) == 31


def test_benefit_item_defaults():
    item = BenefitItem(
        id="test_1",
        title="2026 평생교육이용권",
        category="교육/바우처",
        organization="교육부",
        summary="연 35만원 평생교육 강좌 수강료 지원",
        apply_period_text="2026-10-20 ~ 2026-11-05",
        start_date="2026-10-20",
        end_date="2026-11-05",
    )
    assert item.region == "전국"
    assert item.is_always_open is False


def test_filter_and_classify_benefits():
    config = {
        "profile": {
            "birth_year": 1995,
            "region_sido": "서울",
            "region_sigungu": "강남구",
            "include_nationwide": True,
            "include_age_unrestricted": True,
        },
        "interests": {
            "priority_keywords": ["평생교육", "적금"],
            "exclude_keywords": ["농업인"],
        },
        "notification": {
            "closing_soon_days": 3,
        },
    }

    items = [
        BenefitItem(
            id="b1",
            title="2026 청년내일저축계좌 적금",
            category="청년/금융",
            organization="보건복지부",
            summary="월 10만원 저축 시 정부지원금 매칭",
            apply_period_text="2026-10-25 ~ 2026-11-15",
            start_date="2026-10-25",
            end_date="2026-11-15",
            min_age=19,
            max_age=34,
            region="전국",
        ),
        BenefitItem(
            id="b2",
            title="강남구 청년 자격증 응시료 지원",
            category="지자체지원",
            organization="서울 강남구",
            summary="어학 및 자격증 시험 응시료 연 10만원 지원",
            apply_period_text="2026-10-01 ~ 2026-10-28",
            start_date="2026-10-01",
            end_date="2026-10-28",
            min_age=19,
            max_age=39,
            region="서울 강남구",
        ),
        BenefitItem(
            id="b3",
            title="부산 청년 월세 지원",
            category="주거/생활",
            organization="부산광역시",
            summary="월 20만원 지원",
            apply_period_text="2026-10-01 ~ 2026-11-30",
            start_date="2026-10-01",
            end_date="2026-11-30",
            region="부산",
        ),
        BenefitItem(
            id="b4",
            title="어르신 효도 바우처",
            category="지자체지원",
            organization="서울시",
            summary="65세 이상 지원",
            apply_period_text="상시",
            is_always_open=True,
            min_age=65,
            region="서울",
        ),
        BenefitItem(
            id="b5",
            title="청년 농업인 영농정착 지원금",
            category="청년/금융",
            organization="농림축산식품부",
            summary="영농 정착 지원",
            apply_period_text="2026-10-01 ~ 2026-11-10",
            start_date="2026-10-01",
            end_date="2026-11-10",
            region="전국",
        ),
    ]

    result = filter_and_classify_benefits(
        items=items,
        config=config,
        seen_ids={"b2"},
        today=date(2026, 10, 26),
    )

    assert len(result.newly_opened) == 1
    assert result.newly_opened[0].id == "b1"
    assert result.newly_opened[0].is_priority is True

    assert len(result.closing_soon) == 1
    assert result.closing_soon[0].id == "b2"
    assert result.closing_soon[0].d_day == 2
