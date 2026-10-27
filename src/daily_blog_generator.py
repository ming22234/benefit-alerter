import base64
from datetime import date
import html
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.blog_image_generator import (
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


def map_blog_category(item_category: str, title: str) -> str:
    """사용자 블로그 4대 카테고리(돈·지원금 NEW / 건강·접종 / 살림·생활 / 폰·행정) 자동 매핑"""
    combined = f"{item_category} {title}"
    if any(k in combined for k in ["건강", "접종", "검진", "백신", "의료", "병원", "치료"]):
        return "건강·접종"
    if any(k in combined for k in ["모바일", "신분증", "민원", "등본", "증명서", "통신"]):
        return "폰·행정"
    if any(k in combined for k in ["패스", "교통", "전기", "가스", "수도", "다자녀", "문화누리"]):
        return "돈·지원금 NEW (또는 살림·생활)"
    return "돈·지원금 NEW"


def _encode_png_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _extract_short_amount(summary: str) -> str:
    m = re.search(r"((?:최대\s*)?\d[\d,]*\s*만\s*원|\d{1,2}%)", summary)
    if m:
        return f"{m.group(1).strip()} 지원 혜택"
    return "핵심 지원 혜택 정리"


def _clean_short_title(title: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", title).strip()[:16]


def build_blog_package_for_today(today: Optional[date] = None) -> Dict[str, Any]:
    ref_today = today or date.today()
    today_str = ref_today.strftime("%Y-%m-%d")

    candidates = pick_candidates(top_n=10)
    if not candidates:
        # 모든 후보를 다 썼으면 히스토리 초기화 후 재선정
        if BLOG_HISTORY_PATH.exists():
            BLOG_HISTORY_PATH.unlink()
        candidates = pick_candidates(top_n=5)

    chosen = candidates[0]
    bid = chosen["id"]
    raw_title = chosen["title"]
    short_name = re.sub(r"\s*\([^)]*\)", "", raw_title).strip()
    org = chosen["organization"]
    region_label = chosen["blog_region"]
    target_text = chosen["target_summary"]
    benefit_text = chosen["summary"]
    period_text = chosen["apply_period_text"]
    detail_url = chosen["url"]
    apply_url = chosen.get("apply_url") or detail_url

    blog_cat = map_blog_category(chosen["category"], raw_title)
    amount_highlight = _extract_short_amount(benefit_text)

    # 추천 제목 3선
    titles = [
        f"2026 {short_name} 신청 자격과 방법, {amount_highlight} 놓치지 마세요",
        f"{short_name} 지원 대상 및 신청 기간, 온라인 접수 절차 정리",
        f"모르면 놓치는 {short_name}, 지원 금액부터 필수 서류까지 한눈에 보기",
    ]

    # 이미지 2장 생성
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r"[^a-zA-Z0-9가-힣]+", "-", short_name).strip("-")[:24]
    thumb_path = IMG_DIR / f"{today_str}_{slug}_thumbnail.png"
    info_path = IMG_DIR / f"{today_str}_{slug}_infographic.png"

    generate_benefit_thumbnail(
        out_path=thumb_path,
        badge_text=f"2026 알짜 혜택 · {region_label}",
        title_line1=_clean_short_title(short_name),
        highlight_line2=amount_highlight[:14],
        sub_title="지원 대상 · 신청 방법 · 기간 핵심 가이드",
        check_items=[
            f"대상: {target_text[:28]}",
            f"혜택: {benefit_text[:28]}",
            f"기관: {org[:28]}",
        ],
        footer_text=f"[신청일정] {period_text[:30]}",
    )

    generate_benefit_infographic(
        out_path=info_path,
        header_tag="한눈에 보는 신청 요약표",
        header_title=f"2026 {short_name[:16]} 핵심 정리",
        rows=[
            ("01. 지원 대상", target_text[:28], target_text[28:66] or f"{region_label} 대상자 신청 가능"),
            ("02. 지원 혜택", benefit_text[:28], benefit_text[28:66] or "상세 지원 금액 및 혜택 공고 참조"),
            ("03. 주관 기관", org[:28], f"지역 범위: {region_label}"),
            ("04. 신청 기간", period_text[:28], period_text[28:66] or "예산 소진 전 신청 권장"),
            ("05. 신청 방법", "공식 온라인 접수창구 신청", apply_url[:48]),
        ],
        tip_title="신청 전 미리 챙겨야 할 필수 체크포인트 3가지",
        tip_lines=[
            "① 본인 연령·거주지·소득 기준이 공고 요건에 부합하는지 확인",
            "② 온라인 신청 시 공공 마이데이터 연동 동의하면 서류 제출 간소화",
            "③ 예산 소진 시 조기 마감될 수 있으므로 접수 기간 내 빠른 신청 권장",
        ],
    )

    thumb_b64 = _encode_png_base64(thumb_path)
    info_b64 = _encode_png_base64(info_path)

    hashtags = [
        f"#{re.sub(r'[^가-힣a-zA-Z0-9]', '', short_name)}",
        "#정부지원금",
        "#2026지원금",
        "#청년지원금",
        "#바우처신청",
        "#생활꿀팁",
        "#지원금신청방법",
        "#복지혜택",
        "#보조금24",
        "#재테크꿀팁",
    ]
    hashtag_str = " ".join(dict.fromkeys(hashtags))

    # 1) 순수 텍스트 원고 (.md - 마크다운 기호 ** 전혀 없음, 짧은 호흡 줄바꿈)
    md_content = f"""[블로그 발행 카테고리]
👉 {blog_cat}
(전체 카테고리 목록: 돈·지원금 NEW / 건강·접종 / 살림·생활 / 폰·행정)

[추천 블로그 제목 3선 - 마음에 드는 제목 1개를 복사해 제목란에 붙여넣으세요]
1. {titles[0]}
2. {titles[1]}
3. {titles[2]}


==========================================================
[본문 시작 - 아래부터 끝까지 복사해서 네이버 블로그에 붙여넣으세요]
==========================================================

요즘 물가도 오르고 고정 지출이 늘어나면서
내가 받을 수 있는 정부나 지자체 지원금이 없는지
찾아보시는 분들이 정말 많습니다.

그중에서도 조건만 맞으면 꼭 챙겨야 할 알짜 혜택인
'{raw_title}' 신청 정보와 자격 요건을
한눈에 보기 쉽게 정리해 드립니다.

신청 기간을 놓치거나 예산이 소진되면
다음 모집 때까지 기다려야 하니,
아래 지원 대상에 해당하는지 지금 바로 확인해 보세요.



━━━━━━━━━━━━━━━━━━━━━━
■ 한눈에 보는 핵심 요약
━━━━━━━━━━━━━━━━━━━━━━

• 사업 명칭
  {raw_title}

• 주관 기관
  {org} ({region_label})

• 지원 대상
  {target_text}

• 지원 혜택
  {benefit_text}

• 신청 기간
  {period_text}

• 상세 안내 페이지
  {detail_url}

• 온라인 신청 창구
  {apply_url}



━━━━━━━━━━━━━━━━━━━━━━
■ 1. 내가 대상자일까? 지원 자격 체크리스트
━━━━━━━━━━━━━━━━━━━━━━

가장 먼저 확인해야 할 부분은
내가 신청 대상에 포함되는지 여부입니다.


① 기본 대상 및 연령 요건
이번 '{short_name}' 사업의 기본 지원 대상은
{target_text}입니다.

본인의 주민등록상 출생연도(만 나이)와 거주지 조건이
해당 기준에 부합하는지 먼저 체크해 보세요.


② 지역 및 세부 기준 확인
이 사업은 {region_label} 기준으로 운영되며,
세부 자격 요건은 주관 기관인 {org} 공고문을 따릅니다.

신청 페이지에서 본인 인증을 거치면
대상 여부를 빠르게 조회할 수 있습니다.



━━━━━━━━━━━━━━━━━━━━━━
■ 2. 얼마나, 어떤 혜택을 받을 수 있나?
━━━━━━━━━━━━━━━━━━━━━━

지원 대상자로 선정되면 받을 수 있는 핵심 혜택은 다음과 같습니다.

• 핵심 지원 내용
  {benefit_text}

직접 현금(계좌 입금)이나 바우처 포인트, 또는 금리·비용 감면 형태로
실질적인 생활비와 자기계발 부담을 크게 덜어주는 혜택이므로
자격이 된다면 반드시 신청해 두는 것이 유리합니다.



━━━━━━━━━━━━━━━━━━━━━━
■ 3. 온라인 신청 방법 및 준비 절차
━━━━━━━━━━━━━━━━━━━━━━

복잡하게 오프라인 창구를 방문할 필요 없이
PC나 스마트폰으로 온라인 신청 창구에서 간편하게 접수할 수 있습니다.


[온라인 신청 순서]

• 1단계 : 공식 상세 안내 및 신청 페이지 접속
  상세 안내 : {detail_url}
  신청 창구 : {apply_url}

• 2단계 : 간편인증 또는 공동·금융인증서 로그인

• 3단계 : 신청서 작성 및 공공 마이데이터 연동 동의
  (마이데이터 연동에 동의하면 주민등록등·초본 등 기본 행정서류가 자동 제출되어 매우 편리합니다.)

• 4단계 : 필수 증빙서류 첨부 및 최종 접수 완료



━━━━━━━━━━━━━━━━━━━━━━
■ 4. 신청 전 꼭 알아야 할 주의사항
━━━━━━━━━━━━━━━━━━━━━━

1) 신청 기한 및 예산 소진 확인
공식 안내된 신청 일정은 '{period_text}'입니다.

단, 많은 지원사업이 배정된 예산 한도 내에서 운영되므로
마감일 직전보다는 여유 있게 미리 접수해 두시는 것을 추천합니다.


2) 지급 일정 및 선정 결과 안내
신청 완료 후 자격 요건 심사를 거쳐 최종 선정 여부가 결정되며,
결과는 신청 시 입력한 휴대폰 문자(알림톡) 또는 홈페이지 마이페이지에서 확인할 수 있습니다.

주변에 해당 조건에 맞는 가족이나 지인이 있다면
이 글을 공유해서 함께 혜택을 챙겨보시기 바랍니다!



━━━━━━━━━━━━━━━━━━━━━━
■ 추천 태그 (복사해서 태그란에 붙여넣으세요)
━━━━━━━━━━━━━━━━━━━━━━
{hashtag_str}
"""

    # 2) 이미지 내장 올인원 HTML 원고 (.html)
    esc = lambda s: html.escape(str(s or ""), quote=True)
    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>[블로그 원고] {esc(short_name)}</title>
<style>
  body {{
    font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
    background: #f1f5f9;
    color: #1e293b;
    margin: 0;
    padding: 24px 14px;
    line-height: 1.85;
  }}
  .toolbar {{
    max-width: 800px;
    margin: 0 auto 18px;
    background: #0f172a;
    color: #fff;
    padding: 18px 22px;
    border-radius: 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }}
  .btn-group {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .btn {{
    border: none;
    padding: 10px 16px;
    font-size: 14px;
    font-weight: 700;
    border-radius: 8px;
    cursor: pointer;
    text-decoration: none;
    display: inline-block;
  }}
  .btn-copy {{ background: #03c75a; color: #fff; }}
  .btn-dl {{ background: #3b82f6; color: #fff; }}
  .paper {{
    max-width: 800px;
    margin: 0 auto;
    background: #fff;
    padding: 36px 32px;
    border-radius: 14px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.06);
  }}
  .meta-box {{
    background: #f8fafc;
    border: 1px dashed #94a3b8;
    padding: 18px 20px;
    border-radius: 10px;
    margin-bottom: 28px;
  }}
  .img-preview-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 28px;
    background: #f8fafc;
    padding: 16px;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
  }}
  .img-card {{ text-align: center; }}
  .img-card img {{ max-width: 100%; height: auto; border-radius: 8px; border: 1px solid #cbd5e1; }}
  @media (max-width: 640px) {{
    .img-preview-grid {{ grid-template-columns: 1fr; }}
    .paper {{ padding: 24px 18px; }}
  }}
</style>
</head>
<body>

<div class="toolbar">
  <div>
    <strong>📝 오늘의 혜택 블로그 올인원 패키지 ({esc(today_str)})</strong><br>
    <span style="font-size:13px; color:#cbd5e1;">이미지 2장 저장 + 본문 서식 1클릭 복사 후 네이버 블로그에 <b>Ctrl+V</b> 하세요!</span>
  </div>
  <div class="btn-group">
    <a class="btn btn-dl" href="data:image/png;base64,{thumb_b64}" download="{today_str}_thumbnail.png">💾 썸네일 저장</a>
    <a class="btn btn-dl" href="data:image/png;base64,{info_b64}" download="{today_str}_infographic.png">💾 요약표 이미지 저장</a>
    <button class="btn btn-copy" onclick="copyBlogContent()">📋 본문 서식 통째로 복사</button>
  </div>
</div>

<div class="paper">
  <div class="meta-box">
    <div style="margin-bottom:12px; padding-bottom:10px; border-bottom:1px solid #cbd5e1;">
      <strong>📂 발행 카테고리 선택 :</strong>
      <span style="background:#2563eb; color:#fff; padding:4px 10px; border-radius:6px; font-weight:bold; font-size:14px; margin-left:6px;">{esc(blog_cat)}</span>
      <span style="font-size:13px; color:#64748b; margin-left:8px;">(목록: 돈·지원금 NEW / 건강·접종 / 살림·생활 / 폰·행정)</span>
    </div>
    <strong>💡 추천 제목 3선 (마음에 드는 제목 1개를 복사해 제목란에 붙여넣으세요)</strong>
    <ol style="margin:8px 0 0 0; padding-left:20px;">
      <li><b>{esc(titles[0])}</b></li>
      <li><b>{esc(titles[1])}</b></li>
      <li><b>{esc(titles[2])}</b></li>
    </ol>
  </div>

  <!-- 여기서부터 네이버 블로그에 복사되는 본문 영역 (이미지 2장 본문 내 직접 포함) -->
  <div id="blog-body">
    <p style="text-align:center; margin:0 0 24px 0;">
      <img src="data:image/png;base64,{thumb_b64}" alt="{esc(short_name)} 대표 썸네일" style="max-width:100%; width:640px; height:auto; border-radius:12px; border:1px solid #cbd5e1;">
    </p>

    <p style="font-size:16px; line-height:1.9;">
      요즘 물가도 오르고 고정 지출이 늘어나면서<br>
      내가 받을 수 있는 정부나 지자체 지원금이 없는지<br>
      찾아보시는 분들이 정말 많습니다.
    </p>

    <p style="font-size:16px; line-height:1.9;">
      그중에서도 조건만 맞으면 꼭 챙겨야 할 알짜 혜택인<br>
      <strong>'{esc(raw_title)}'</strong> 신청 정보와 자격 요건을<br>
      한눈에 보기 쉽게 정리해 드립니다.
    </p>

    <p style="font-size:16px; line-height:1.9;">
      신청 기간을 놓치거나 예산이 소진되면<br>
      다음 모집 때까지 기다려야 하니,<br>
      아래 지원 대상에 해당하는지 지금 바로 확인해 보세요.
    </p>

    <br>

    <h3 style="font-size:20px; color:#0f172a; border-left:5px solid #2563eb; padding-left:12px;">📌 한눈에 보는 핵심 요약</h3>
    <table style="width:100%; border-collapse:collapse; margin:16px 0; font-size:15px;">
      <tbody>
        <tr>
          <td style="width:26%; background:#f1f5f9; padding:12px 14px; border:1px solid #cbd5e1; font-weight:bold;">🎯 지원 대상</td>
          <td style="padding:12px 14px; border:1px solid #cbd5e1;"><strong>{esc(target_text)}</strong></td>
        </tr>
        <tr>
          <td style="background:#f1f5f9; padding:12px 14px; border:1px solid #cbd5e1; font-weight:bold;">💰 지원 혜택</td>
          <td style="padding:12px 14px; border:1px solid #cbd5e1;"><strong>{esc(benefit_text)}</strong></td>
        </tr>
        <tr>
          <td style="background:#f1f5f9; padding:12px 14px; border:1px solid #cbd5e1; font-weight:bold;">🏛 주관 기관</td>
          <td style="padding:12px 14px; border:1px solid #cbd5e1;">{esc(org)} ({esc(region_label)})</td>
        </tr>
        <tr>
          <td style="background:#f1f5f9; padding:12px 14px; border:1px solid #cbd5e1; font-weight:bold;">🗓 신청 기간</td>
          <td style="padding:12px 14px; border:1px solid #cbd5e1;"><strong>{esc(period_text)}</strong></td>
        </tr>
        <tr>
          <td style="background:#f1f5f9; padding:12px 14px; border:1px solid #cbd5e1; font-weight:bold;">🖥 신청 창구</td>
          <td style="padding:12px 14px; border:1px solid #cbd5e1;">
            <a href="{esc(detail_url)}" target="_blank" style="color:#2563eb; font-weight:bold;">👉 [상세 공고문 확인하기]</a><br>
            <a href="{esc(apply_url)}" target="_blank" style="color:#059669; font-weight:bold;">⚡ [온라인 신청 창구 바로가기]</a>
          </td>
        </tr>
      </tbody>
    </table>

    <br>

    <p style="text-align:center; margin:20px 0 28px 0;">
      <img src="data:image/png;base64,{info_b64}" alt="{esc(short_name)} 핵심 요약 인포그래픽" style="max-width:100%; width:680px; height:auto; border-radius:12px; border:1px solid #cbd5e1;">
    </p>

    <h3 style="font-size:20px; color:#0f172a; border-left:5px solid #2563eb; padding-left:12px;">1. 내가 대상자일까? 지원 자격 체크리스트</h3>
    <p style="font-size:16px; line-height:1.9;">
      가장 먼저 확인해야 할 부분은<br>
      내가 신청 대상에 포함되는지 여부입니다.
    </p>
    <p style="font-size:16px; line-height:1.9;">
      <strong>① 기본 대상 및 연령 요건</strong><br>
      이번 <strong>'{esc(short_name)}'</strong> 사업의 지원 대상은<br>
      <strong>{esc(target_text)}</strong>입니다.<br><br>
      본인의 주민등록상 출생연도(만 나이)와 기본 조건이<br>
      해당 기준에 부합하는지 먼저 체크해 보세요.
    </p>
    <p style="font-size:16px; line-height:1.9;">
      <strong>② 지역 및 세부 요건</strong><br>
      이 사업은 <strong>{esc(region_label)}</strong> 기준으로 운영되며,<br>
      세부 자격 요건은 주관 기관인 <strong>{esc(org)}</strong> 공고문을 따릅니다.<br><br>
      온라인 신청 페이지에서 본인 인증을 거치면<br>
      대상자 해당 여부를 간편하게 조회할 수 있습니다.
    </p>

    <br>

    <h3 style="font-size:20px; color:#0f172a; border-left:5px solid #2563eb; padding-left:12px;">2. 얼마나, 어떤 혜택을 받을 수 있나?</h3>
    <p style="font-size:16px; line-height:1.9;">
      지원 대상자로 선정되면 받을 수 있는 핵심 혜택은 다음과 같습니다.
    </p>
    <div style="background:#f8fafc; border-left:4px solid #2563eb; padding:18px 22px; margin:16px 0; font-size:16px; line-height:1.85;">
      <strong>💰 핵심 지원 내용</strong><br><br>
      • {esc(benefit_text)}
    </div>
    <p style="font-size:16px; line-height:1.9;">
      직접 지원금이나 바우처 포인트, 또는 우대 금융·비용 환급 형태로<br>
      실질적인 생활비와 자기계발 부담을 크게 덜어주는 제도이므로<br>
      자격 요건이 된다면 반드시 챙겨두는 것이 유리합니다.
    </p>

    <br>

    <h3 style="font-size:20px; color:#0f172a; border-left:5px solid #2563eb; padding-left:12px;">3. 온라인 신청 방법 및 준비 절차</h3>
    <p style="font-size:16px; line-height:1.9;">
      오프라인 창구에 직접 방문할 필요 없이 스마트폰이나 PC로<br>
      공식 온라인 접수 페이지에서 간편하게 신청할 수 있습니다.
    </p>
    <p style="font-size:16px; line-height:1.9;">
      <strong>📌 온라인 신청 4단계</strong><br><br>
      <strong>1단계 : 공식 상세 안내 및 신청 페이지 접속</strong><br>
      • 상세 안내 : <a href="{esc(detail_url)}" target="_blank" style="color:#2563eb;">{esc(detail_url)}</a><br>
      • 신청 창구 : <a href="{esc(apply_url)}" target="_blank" style="color:#059669;">{esc(apply_url)}</a><br><br>
      <strong>2단계 : 간편인증 또는 공동·금융인증서 로그인</strong><br><br>
      <strong>3단계 : 신청서 작성 및 공공 마이데이터 연동 동의</strong><br>
      (마이데이터 연동에 동의하면 주민등록등·초본 등 기본 행정서류가 자동 제출되어 매우 편리합니다.)<br><br>
      <strong>4단계 : 구비서류 확인 및 최종 접수 완료</strong>
    </p>

    <br>

    <h3 style="font-size:20px; color:#0f172a; border-left:5px solid #2563eb; padding-left:12px;">4. 신청 전 꼭 알아야 할 주의사항</h3>
    <p style="font-size:16px; line-height:1.9;">
      <strong>1) 신청 기한 및 예산 소진 여부 확인</strong><br>
      공식 안내된 신청 일정은 <strong>'{esc(period_text)}'</strong>입니다.<br><br>
      단, 많은 지원사업이 배정된 예산 한도 내에서 선착순으로 운영되므로<br>
      마감일 직전보다는 여유 있게 미리 접수해 두시는 것을 추천합니다.<br><br>
      <strong>2) 주변 지인에게도 공유해 보세요</strong><br>
      몰라서 신청하지 못하면 그대로 사라지는 혜택인 만큼,<br>
      주변에 해당 조건에 맞는 가족이나 친구가 있다면 함께 공유해 보시기 바랍니다!
    </p>

    <br>
    <p style="font-size:14px; color:#64748b;">
      {esc(hashtag_str)}
    </p>
  </div>
</div>

<script>
function copyBlogContent() {{
  const el = document.getElementById('blog-body');
  const range = document.createRange();
  range.selectNodeContents(el);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  document.execCommand('copy');
  sel.removeAllRanges();
  const btn = document.querySelector('.btn-copy');
  btn.textContent = '✅ 복사 완료! 네이버 블로그에 Ctrl+V 하세요';
  setTimeout(() => {{ btn.textContent = '📋 본문 서식 통째로 복사'; }}, 3000);
}}
</script>
</body>
</html>
"""

    md_path = BLOG_DIR / f"{today_str}_{slug}.md"
    html_path = BLOG_DIR / f"{today_str}_{slug}.html"
    md_path.write_text(md_content, encoding="utf-8")
    html_path.write_text(html_content, encoding="utf-8")

    save_blog_history(bid, raw_title, f"blog_posts/{html_path.name}")

    return {
        "id": bid,
        "title": raw_title,
        "blog_category": blog_cat,
        "recommended_title": titles[0],
        "md_path": md_path,
        "html_path": html_path,
        "thumb_path": thumb_path,
        "info_path": info_path,
    }


def embed_images_into_existing_html_and_send() -> bool:
    from src.notifier import send_telegram_blog_package

    thumb_p = IMG_DIR / "2026-10-27_thumbnail.png"
    info_p = IMG_DIR / "2026-10-27_infographic.png"
    html_p = BLOG_DIR / "2026-10-27_gyeonggi-youth-exam-support.html"
    md_p = BLOG_DIR / "2026-10-27_gyeonggi-youth-exam-support.md"

    tb64 = _encode_png_base64(thumb_p)
    ib64 = _encode_png_base64(info_p)

    txt = html_p.read_text(encoding="utf-8")
    if "data:image/png;base64" not in txt:
        top_img = (
            f'<div id="blog-body">\n'
            f'    <p style="text-align:center; margin:0 0 24px 0;">\n'
            f'      <img src="data:image/png;base64,{tb64}" alt="대표 썸네일" style="max-width:100%; width:640px; height:auto; border-radius:12px; border:1px solid #cbd5e1;">\n'
            f'    </p>'
        )
        mid_img = (
            f'    <p style="text-align:center; margin:20px 0 28px 0;">\n'
            f'      <img src="data:image/png;base64,{ib64}" alt="본문 요약 인포그래픽" style="max-width:100%; width:680px; height:auto; border-radius:12px; border:1px solid #cbd5e1;">\n'
            f'    </p>\n\n'
            f'    <h3 style="font-size:20px; color:#0f172a; border-left:5px solid #2563eb; padding-left:12px;">1. 내가 대상자일까?'
        )
        txt = txt.replace('<div id="blog-body">', top_img, 1)
        txt = txt.replace(
            '    <h3 style="font-size:20px; color:#0f172a; border-left:5px solid #2563eb; padding-left:12px;">1. 내가 대상자일까?',
            mid_img,
            1,
        )
        html_p.write_text(txt, encoding="utf-8")

    pkg = {
        "id": "seed_gyeonggi_exam_fee",
        "title": "경기청년 역량강화 기회지원 (어학·자격증 비용 지원)",
        "blog_category": "돈·지원금 NEW",
        "recommended_title": "토익 자격증 시험비 30만원 현금 환급, 2026 경기청년 역량강화 기회지원 신청 자격과 방법",
        "md_path": md_p,
        "html_path": html_p,
        "thumb_path": thumb_p,
        "info_path": info_p,
    }
    return send_telegram_blog_package(pkg)


if __name__ == "__main__":
    sent = embed_images_into_existing_html_and_send()
    print(f"[DONE] Sent existing blog package to Telegram: {sent}")
