from datetime import date
from src.models import BenefitItem, ClassifiedBenefits
from src.notifier import format_daily_briefing, split_message_chunks


def test_format_daily_briefing_and_chunking():
    classified = ClassifiedBenefits(
        newly_opened=[
            BenefitItem(
                id="b1",
                title="2026 평생교육이용권 2차 신청",
                category="교육/바우처",
                organization="교육부",
                summary="연 35만원 평생교육 강좌 수강료 지원",
                apply_period_text="2026-10-26 ~ 2026-11-08",
                start_date="2026-10-26",
                end_date="2026-11-08",
                url="https://www.lllcard.kr",
                is_priority=True,
                d_day=13,
            )
        ]
    )
    config = {
        "profile": {
            "birth_year": 1995,
            "region_sido": "서울",
            "region_sigungu": "강남구",
        },
        "notification": {
            "max_other_items_in_message": 10,
        },
    }

    msg = format_daily_briefing(classified, config, today=date(2026, 10, 26))
    assert "평생교육이용권" in msg
    assert "https://www.lllcard.kr" in msg
    assert "서울 강남구" in msg

    chunks = split_message_chunks(msg, max_length=100)
    assert all(len(c) <= 100 for c in chunks)
