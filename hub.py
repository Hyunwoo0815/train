import json
import os
import sys
import argparse
from urllib.parse import quote
from datetime import datetime, timezone, timedelta
import re

# 한국 시간대 설정
KST = timezone(timedelta(hours=9))


def create_hub_page(json_path, output_dir="html_output", site_base_url="https://train.medilocator.co.kr", use_html_extension=False):
    """
    허브 페이지 생성 함수
    
    Args:
        json_path: JSON 파일 경로
        output_dir: 출력 디렉토리
        site_base_url: 사이트 기본 URL
        use_html_extension: True면 .html 확장자 사용, False면 확장자 없이
    """
    print(f"✅ 페이지 생성 시작: {json_path}")

    if not os.path.exists(json_path) or os.path.getsize(json_path) == 0:
        print(f"⛔ 파일이 존재하지 않거나 비어 있음: {json_path}")
        return False

    # JSON 파일 로드
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"📄 JSON 파일 로드 성공: {os.path.basename(json_path)}")
    except json.JSONDecodeError as e:
        print(f"❌ JSON 파싱 실패: {json_path} - {e}")
        return False
    except Exception as e:
        print(f"❌ 파일 읽기 실패: {json_path} - {e}")
        return False

    from_station = data.get("출발역", "")
    destinations = data.get("도착지", [])
    
    if not from_station:
        print(f"⚠️ 출발역 정보가 없습니다: {json_path}")
        return False
    
    if not destinations:
        print(f"⚠️ 도착지 정보가 없습니다: {json_path}")
        return False
    
    # '역' 처리
    from_station_clean = from_station.replace("역", "")
    from_station_with_station = from_station if from_station.endswith("역") else from_station + "역"
    
    cleaned_destinations = [d.replace("역", "") for d in destinations]
    
    print(f"🚉 처리 중: {from_station_with_station} → {len(destinations)}개 도착지")

    # 출력 디렉토리 생성
    os.makedirs(output_dir, exist_ok=True)
    
    # 파일명 생성
    base_filename = f"{from_station_with_station}에서-출발하는-열차시간표"
    if use_html_extension:
        filename = f"{base_filename}.html"
        filepath = os.path.join(output_dir, filename)
    else:
        filename = base_filename
        filepath = os.path.join(output_dir, filename)

    # 메타데이터 처리 - 발행일/수정일 관리 (한국 시간 기준)
    meta_file = os.path.join(output_dir, "meta.json")
    
    # 기존 메타데이터 로드
    if os.path.exists(meta_file) and os.path.getsize(meta_file) > 0:
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
                print(f"   📋 기존 메타데이터 로드 완료")
        except json.JSONDecodeError:
            print(f"⚠️ meta.json 파싱 오류. 새로 생성합니다.")
            meta_data = {}
    else:
        meta_data = {}

    # 한국 시간 기준으로 날짜/시간 생성
    now_kst = datetime.now(KST)
    today = now_kst.strftime("%Y-%m-%d")
    current_time = now_kst.strftime("%Y-%m-%d %H:%M:%S KST")
    iso_time = now_kst.isoformat()  # ISO 8601 형식 (메타태그용)
    
    meta_key = base_filename
    
    # 기존 데이터에서 최초 발행일 유지
    existing_entry = meta_data.get(meta_key, {})
    created_date = existing_entry.get("created", today)
    created_iso = existing_entry.get("created_iso", iso_time)
    
    # 파일 존재 여부 확인
    file_exists = os.path.exists(filepath)
    
    # 메타데이터 구조 - 발행일 유지, 수정일 업데이트
    meta_entry = {
        "created": created_date,      # 최초 발행일 유지 (YYYY-MM-DD)
        "created_iso": created_iso,   # ISO 8601 형식 (메타태그용)
        "modified": today,            # 마지막 수정일 (YYYY-MM-DD)
        "modified_iso": iso_time,     # ISO 8601 형식 (메타태그용)
        "last_build": current_time,   # 마지막 빌드 시간 (KST 명시)
        "timezone": "Asia/Seoul",     # 시간대 정보
        "route": f"{from_station_with_station} → 출발지 목록",
        "total_destinations": len(destinations),
        "filename": filename if use_html_extension else f"{filename}.html",
        "url_slug": base_filename,
        "build_count": existing_entry.get("build_count", 0) + 1,  # 빌드 횟수
        "status": "updated" if file_exists else "created"  # 생성/업데이트 상태
    }
    
    meta_data[meta_key] = meta_entry
    
    # 로그 출력 (한국 시간 표시)
    if file_exists:
        print(f"   🔄 기존 파일 덮어쓰기 (최초 발행: {created_date} KST)")
    else:
        print(f"   ✨ 새 파일 생성 (발행일: {created_date} KST)")
    
    print(f"   🕐 현재 시간: {current_time}")

    # 도착지 링크 생성
    matching_links = []
    for destination in destinations:
        dest_clean = destination.replace("역", "")
        dest_with_station = destination if destination.endswith("역") else destination + "역"
        
        route_base = f"{from_station_with_station}에서-{dest_with_station}-가는-열차시간표"
        if use_html_extension:
            route_filename = f"{route_base}.html"
        else:
            route_filename = route_base
            
        matching_links.append((dest_clean, route_filename, route_base))

    # SEO를 위한 메타 정보
    top_n = 12
    popular_destinations = ["서울", "부산", "대구", "광주", "대전", "울산", "인천", "수원", "창원", "고양"]
    available_popular = [dest for dest in popular_destinations if dest in cleaned_destinations]
    
    if available_popular:
        top_dest_text = ", ".join(available_popular[:top_n])
    else:
        top_dest_text = ", ".join(dest for dest, _, _ in matching_links[:top_n]) if matching_links else "전국 주요 도시"
    
    description = f"{from_station_with_station}에서 출발하는 KTX, SRT, ITX, 무궁화호 등 모든 열차 시간표를 실시간으로 확인하세요. {top_dest_text} 등 전국 주요 도시로 가는 열차 정보를 제공합니다."
    keywords = f"{from_station_with_station}, {from_station_with_station} 열차시간표, {from_station_with_station} KTX, {from_station_with_station} SRT, 기차시간표, 열차예매, {top_dest_text}"

    canonical_url = f"{site_base_url}/{base_filename}"
    
    # JSON-LD 구조화 데이터
    json_ld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"{from_station_with_station}에서 출발하는 열차 시간표",
        "description": description,
        "url": canonical_url,
        "mainEntity": {
            "@type": "ItemList",
            "name": f"{from_station_with_station}에서 출발하는 열차 목록",
            "numberOfItems": len(matching_links),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": idx + 1,
                    "item": {
                        "@type": "Schedule",
                        "name": f"{from_station_with_station} → {to_station}역 열차 시간표",
                        "url": f"{site_base_url}/{route_base}",
                        "description": f"{from_station_with_station}에서 {to_station}역으로 가는 모든 열차의 출발시간, 도착시간, 소요시간 정보"
                    }
                }
                for idx, (to_station, _, route_base) in enumerate(matching_links)
            ]
        },
        "breadcrumb": {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "name": "홈",
                    "item": site_base_url
                },
                {
                    "@type": "ListItem",
                    "position": 2,
                    "name": f"{from_station_with_station} 출발 열차시간표",
                    "item": canonical_url
                }
            ]
        },
        "publisher": {
            "@type": "Organization",
            "name": "레일가이드",
            "url": site_base_url
        },
        "datePublished": created_date,
        "dateModified": today,
        "inLanguage": "ko-KR"
    }

    # HTML 파일 생성 - 강제 덮어쓰기 모드
    try:
        # 기존 파일이 있으면 백업 정보 로그
        if os.path.exists(filepath):
            file_size = os.path.getsize(filepath)
            print(f"   🔄 기존 파일 덮어쓰기: {os.path.basename(filepath)} ({file_size} bytes)")
        
        with open(filepath, "w", encoding="utf-8") as f:
            route_links_html = ""
            if matching_links:
                for to_station, route_filename, route_base in matching_links:
                    route_links_html += f"""
                    <li class="route-item">
                        <a href="{route_base}" class="route-link">
                            <div>
                                <span class="route-icon">🚄</span>
                                {from_station_with_station} → {to_station}역
                            </div>
                            <span class="route-arrow">→</span>
                        </a>
                    </li>"""
                route_content = f'<ul class="route-list">{route_links_html}</ul>'
            else:
                route_content = '<div class="no-routes">현재 이용 가능한 노선 정보를 준비 중입니다.</div>'
            
            f.write(f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="index, follow">
  <meta name="googlebot" content="index, follow">
  
  <!-- Google AdSense -->
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6101143022477538"
     crossorigin="anonymous"></script>
     
  <!-- SEO Meta Tags (name 속성) -->
  <title>{from_station_with_station}에서 출발하는 열차 시간표 | 실시간 KTX SRT 무궁화호 정보</title>
  <meta name="description" content="{description}">
  <meta name="keywords" content="{keywords}">
  <meta name="author" content="레일가이드">
  <meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
  <meta name="googlebot" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
  
  <!-- Article Meta (name 속성) -->
  <meta name="article:published_time" content="{created_iso}">
  <meta name="article:modified_time" content="{meta_entry['modified_iso']}">
  <meta name="article:author" content="레일가이드">
  <meta name="article:section" content="교통">
  <meta name="article:tag" content="기차시간표, KTX, SRT, 열차예약">
  
  <!-- Business/Location Meta (name 속성) -->
  <meta name="geo.region" content="KR">
  <meta name="geo.country" content="Korea">
  <meta name="geo.placename" content="{from_station_clean}">
  <meta name="ICBM" content="37.566535, 126.9779692">
  
  <!-- Content Meta (name 속성) -->
  <meta name="subject" content="열차 시간표">
  <meta name="copyright" content="레일가이드 2025">
  <meta name="language" content="ko">
  <meta name="revised" content="{today}">
  <meta name="last-modified" content="{meta_entry['modified_iso']}">
  <meta name="created" content="{created_iso}">
  <meta name="abstract" content="{from_station_with_station} 출발 열차 시간표">
  <meta name="topic" content="교통, 기차, 열차시간표">
  <meta name="summary" content="{description}">
  <meta name="Classification" content="Business">
  <meta name="designer" content="레일가이드">
  <meta name="reply-to" content="contact@medilocator.co.kr">
  <meta name="owner" content="레일가이드">
  <meta name="url" content="{canonical_url}">
  <meta name="identifier-URL" content="{canonical_url}">
  <meta name="directory" content="submission">
  <meta name="category" content="교통">
  <meta name="coverage" content="Worldwide">
  <meta name="distribution" content="Global">
  <meta name="rating" content="General">
  <meta name="revisit-after" content="1 days">
  <meta name="target" content="all">
  <meta name="HandheldFriendly" content="True">
  <meta name="MobileOptimized" content="320">
  <meta name="apple-mobile-web-app-title" content="레일가이드">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="format-detection" content="telephone=no">
  
  <!-- SEO Meta Tags (property 속성) -->
  <meta property="title" content="{from_station_with_station}에서 출발하는 열차 시간표 | 실시간 KTX SRT 무궁화호 정보">
  <meta property="description" content="{description}">
  <meta property="keywords" content="{keywords}">
  <meta property="author" content="레일가이드">
  <meta property="type" content="website">
  <meta property="url" content="{canonical_url}">
  <meta property="image" content="{site_base_url}/img/ktx-banner.png">
  <meta property="site_name" content="레일가이드">
  <meta property="locale" content="ko_KR">
  
  <!-- Canonical and Alternate URLs -->
  <link rel="canonical" href="{canonical_url}">
  <link rel="alternate" hreflang="ko" href="{canonical_url}">
  <link rel="alternate" hreflang="ko-KR" href="{canonical_url}">
  <link rel="alternate" hreflang="x-default" href="{canonical_url}">
  
  <!-- Open Graph Meta Tags (property 속성) -->
  <meta property="og:title" content="{from_station_with_station}에서 출발하는 열차 시간표 | 실시간 기차 정보">
  <meta property="og:description" content="{description}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{canonical_url}">
  <meta property="og:image" content="{site_base_url}/img/ktx-banner.png">
  <meta property="og:image:secure_url" content="{site_base_url}/img/ktx-banner.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="{from_station_with_station} 열차시간표 - KTX 고속열차">
  <meta property="og:site_name" content="레일가이드 열차시간표">
  <meta property="og:locale" content="ko_KR">
  <meta property="og:locale:alternate" content="en_US">
  
  <!-- Facebook 추가 Meta Tags (property 속성) -->
  <meta property="fb:admins" content="레일가이드">
  <meta property="fb:app_id" content="레일가이드">
  
  <!-- Article Meta Tags (property 속성) -->
  <meta property="article:published_time" content="{created_iso}">
  <meta property="article:modified_time" content="{meta_entry['modified_iso']}">
  <meta property="article:author" content="레일가이드">
  <meta property="article:section" content="교통">
  <meta property="article:tag" content="기차시간표">
  <meta property="article:tag" content="KTX">
  <meta property="article:tag" content="SRT">
  <meta property="article:tag" content="열차예약">
  <meta property="article:tag" content="{from_station_with_station}">

  <!-- Twitter Card Meta Tags (name 속성) -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{from_station_with_station}에서 출발하는 열차 시간표">
  <meta name="twitter:description" content="{description}">
  <meta name="twitter:image" content="{site_base_url}/img/ktx-banner.png">
  <meta name="twitter:image:alt" content="{from_station_with_station} 열차시간표 정보">
  <meta name="twitter:site" content="@레일가이드">
  <meta name="twitter:creator" content="@레일가이드">
  
  <!-- Twitter 추가 Meta Tags (property 속성) -->
  <meta property="twitter:account_id" content="레일가이드">
  <meta property="twitter:url" content="{canonical_url}">

  <!-- 검색엔진별 최적화 Meta Tags -->
  <!-- Google -->
  <meta name="google" content="nositelinkssearchbox">
  <meta name="google" content="notranslate">
  <meta name="google-site-verification" content="your-google-verification-code">
  
  <!-- Bing -->
  <meta name="msvalidate.01" content="your-bing-verification-code">
  
  <!-- Yandex -->
  <meta name="yandex-verification" content="your-yandex-verification-code">
  
  <!-- Naver -->
  <meta name="naver-site-verification" content="your-naver-verification-code">

  <!-- Additional SEO Meta Tags -->
  <meta name="theme-color" content="#007bff">
  <meta name="msapplication-TileColor" content="#007bff">
  <meta name="msapplication-config" content="browserconfig.xml">
  
  <!-- Dublin Core Meta Tags (name 속성) -->
  <meta name="DC.title" content="{from_station_with_station}에서 출발하는 열차 시간표">
  <meta name="DC.creator" content="레일가이드">
  <meta name="DC.subject" content="열차시간표, 기차예약, 교통정보">
  <meta name="DC.description" content="{description}">
  <meta name="DC.publisher" content="레일가이드">
  <meta name="DC.contributor" content="레일가이드">
  <meta name="DC.date" content="{created_iso}">
  <meta name="DC.date.created" content="{created_iso}">
  <meta name="DC.date.modified" content="{meta_entry['modified_iso']}">
  <meta name="DC.type" content="Text">
  <meta name="DC.format" content="text/html">
  <meta name="DC.identifier" content="{canonical_url}">
  <meta name="DC.source" content="{canonical_url}">
  <meta name="DC.language" content="ko">
  <meta name="DC.relation" content="{site_base_url}">
  <meta name="DC.coverage" content="대한민국">
  <meta name="DC.rights" content="© 2025 레일가이드. All rights reserved.">;

  <!-- Additional Meta Tags -->
  <meta name="geo.region" content="KR">
  <meta name="geo.country" content="Korea">
  <meta name="theme-color" content="#007bff">
  
  <!-- Preconnect for performance -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  
  <!-- Font -->
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">

  <style>
    * {{
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }}
    
    body {{
      font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      max-width: 800px;
      margin: 0 auto;
      padding: 20px;
      line-height: 1.6;
      background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
      color: #333;
      min-height: 100vh;
    }}
    
    .container {{
      background: white;
      border-radius: 12px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.1);
      overflow: hidden;
    }}
    
    header {{
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      padding: 30px 20px;
      text-align: center;
    }}
    
    h1 {{
      font-size: 28px;
      font-weight: 700;
      margin-bottom: 10px;
    }}
    
    .subtitle {{
      font-size: 16px;
      opacity: 0.9;
      font-weight: 300;
    }}
    
    .hero-image {{
      width: 100%;
      height: 200px;
      object-fit: cover;
      display: block;
    }}
    
    .content {{
      padding: 30px 20px;
    }}
    
    .summary-box {{
      background: linear-gradient(135deg, #e3f2fd 0%, #f3e5f5 100%);
      padding: 20px;
      border-radius: 10px;
      margin-bottom: 30px;
      border-left: 4px solid #2196f3;
      font-size: 16px;
      line-height: 1.7;
    }}
    
    .breadcrumb {{
      margin-bottom: 20px;
      font-size: 14px;
      color: #666;
    }}
    
    .breadcrumb a {{
      color: #007bff;
      text-decoration: none;
    }}
    
    .breadcrumb a:hover {{
      text-decoration: underline;
    }}
    
    .route-list {{
      list-style: none;
      display: grid;
      gap: 12px;
    }}
    
    .route-item {{
      transition: transform 0.2s ease, box-shadow 0.2s ease;
    }}
    
    .route-item:hover {{
      transform: translateY(-2px);
    }}
    
    .route-link {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      text-decoration: none;
      background: white;
      padding: 16px 20px;
      border: 2px solid #e9ecef;
      border-radius: 10px;
      color: #495057;
      font-weight: 500;
      font-size: 16px;
      transition: all 0.3s ease;
      box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }}
    
    .route-link:hover {{
      background: #f8f9fa;
      border-color: #007bff;
      color: #007bff;
      box-shadow: 0 4px 16px rgba(0,123,255,0.15);
    }}
    
    .route-icon {{
      font-size: 20px;
      margin-right: 12px;
    }}
    
    .route-arrow {{
      color: #6c757d;
      font-size: 18px;
    }}
    
    .no-routes {{
      text-align: center;
      padding: 40px 20px;
      color: #6c757d;
    }}
    
    footer {{
      background: #f8f9fa;
      padding: 20px;
      text-align: center;
      font-size: 14px;
      color: #6c757d;
      border-top: 1px solid #e9ecef;
    }}
    
    @media (max-width: 768px) {{
      body {{ padding: 10px; }}
      h1 {{ font-size: 24px; }}
      .content {{ padding: 20px 15px; }}
      .route-link {{ padding: 14px 16px; font-size: 15px; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>{from_station_with_station}에서 출발하는 열차 시간표</h1>
      <div class="subtitle">실시간 KTX · SRT · ITX · 무궁화호 정보</div>
    </header>
    
    <img src="img/ktx-banner.png" alt="KTX 고속열차 이미지" class="hero-image">
    
    <div class="content">
      <nav class="breadcrumb" aria-label="breadcrumb">
        <a href="./">홈</a> > 
        <span>{from_station_with_station} 출발 열차시간표</span>
      </nav>
      
      <div class="summary-box">
        <strong>{from_station_with_station}에서 출발하는 모든 열차 정보</strong><br>
        {description}
      </div>
      
      {route_content}
    </div>
    
    <footer>
      <p>&copy; 2025 레일가이드. 모든 열차 시간표 정보는 참고용이며, 정확한 정보는 공식 사이트에서 확인하시기 바랍니다.</p>
      <p>
        최초 발행: {created_date} KST | 
        마지막 업데이트: {today} KST | 
        빌드 #{meta_entry['build_count']} | 
        시간대: Asia/Seoul
      </p>
    </footer>
  </div>

  <script type="application/ld+json">
{json.dumps(json_ld, ensure_ascii=False, indent=2)}
  </script>
</body>
</html>
""")

        print(f"   ✅ HTML 파일 {'덮어쓰기' if file_exists else '생성'} 완료: {os.path.basename(filepath)}")
        print(f"   📊 파일 크기: {os.path.getsize(filepath)} bytes")
        print(f"   📅 발행일: {created_date} KST | 수정일: {today} KST | 빌드: #{meta_entry['build_count']}")
        print(f"   🕐 정확한 시간: {meta_entry['last_build']}")
        
    except Exception as e:
        print(f"   ❌ HTML 파일 생성 실패: {e}")
        return False

    # 메타데이터 저장
    try:
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta_data, f, ensure_ascii=False, indent=2)
        print(f"   ✅ 메타데이터 저장 완료")
    except Exception as e:
        print(f"   ❌ 메타데이터 저장 실패: {e}")

    return True


def process_all_json_in_folder(folder_path, output_dir="html_output", site_base_url="https://train.medilocator.co.kr", use_html_extension=False):
    """폴더 내 모든 JSON 파일 자동 처리"""
    if not os.path.exists(folder_path):
        print(f"❌ 폴더가 존재하지 않습니다: {folder_path}")
        return False
    
    json_files = [f for f in os.listdir(folder_path) if f.endswith(".json")]
    
    if not json_files:
        print(f"⚠️ JSON 파일이 없습니다: {folder_path}")
        return False
    
    print(f"🚀 허브 페이지 생성 시작")
    print(f"📂 입력 폴더: {folder_path}")
    print(f"📁 출력 폴더: {output_dir}")
    print(f"🌐 사이트 URL: {site_base_url}")
    print(f"📄 처리할 JSON 파일 수: {len(json_files)}")
    print(f"🔧 HTML 확장자 사용: {use_html_extension}")
    print(f"💾 덮어쓰기 모드: 활성화")
    print("-" * 60)
    
    success_count = 0
    fail_count = 0
    updated_count = 0
    created_count = 0
    
    for i, file_name in enumerate(json_files, 1):
        file_path = os.path.join(folder_path, file_name)
        print(f"[{i}/{len(json_files)}] 처리 중: {file_name}")
        
        try:
            # 파일 존재 여부 확인 (통계용)
            file_path = os.path.join(folder_path, file_name)
            base_name = os.path.splitext(file_name)[0]
            output_file = os.path.join(output_dir, f"{base_name}역에서-출발하는-열차시간표{'html' if use_html_extension else ''}")
            file_existed = os.path.exists(output_file)
            
            if create_hub_page(file_path, output_dir, site_base_url, use_html_extension):
                success_count += 1
                if file_existed:
                    updated_count += 1
                else:
                    created_count += 1
            else:
                fail_count += 1
        except Exception as e:
            print(f"❌ 파일 처리 실패 {file_name}: {e}")
            fail_count += 1
    
    print("-" * 60)
    print(f"🎉 허브 페이지 생성 완료!")
    print(f"📊 결과 요약:")
    print(f"   ✅ 성공: {success_count}개")
    print(f"   🆕 새로 생성: {created_count}개")
    print(f"   🔄 업데이트: {updated_count}개")
    print(f"   ❌ 실패: {fail_count}개")
    print(f"   📁 출력 폴더: {output_dir}")
    
    return success_count > 0


def main():
    """GitHub Actions 및 CLI에서 사용할 메인 함수"""
    parser = argparse.ArgumentParser(description='기차 허브 페이지 생성기')
    parser.add_argument('--input', '-i', default='cache', help='JSON 파일이 있는 입력 폴더 (기본값: cache)')
    parser.add_argument('--output', '-o', default='html_output', help='HTML 파일을 저장할 출력 폴더 (기본값: html_output)')
    parser.add_argument('--base-url', '-u', default='https://train.medilocator.co.kr', help='사이트 기본 URL')
    parser.add_argument('--html-ext', action='store_true', help='HTML 확장자 사용 (.html)')
    parser.add_argument('--station', '-s', help='특정 역만 처리 (역명 입력)')
    
    args = parser.parse_args()
    
    # 환경변수에서도 설정 읽기 (GitHub Actions용)
    input_folder = os.environ.get('INPUT_FOLDER', args.input)
    output_folder = os.environ.get('OUTPUT_FOLDER', args.output)
    base_url = os.environ.get('SITE_BASE_URL', args.base_url)
    use_html_ext = os.environ.get('USE_HTML_EXTENSION', '').lower() in ['true', '1', 'yes'] or args.html_ext
    target_station = os.environ.get('TARGET_STATION', args.station)
    
    print(f"🚄 기차 허브 페이지 생성기")
    print(f"📂 입력 폴더: {input_folder}")
    print(f"📁 출력 폴더: {output_folder}")
    print(f"🌐 기본 URL: {base_url}")
    print(f"🔧 HTML 확장자: {use_html_ext}")
    
    if target_station:
        # 특정 역만 처리
        print(f"🎯 대상 역: {target_station}")
        possible_files = [
            f"{target_station}.json",
            f"{target_station}역.json",
            f"{target_station.replace('역', '')}.json"
        ]
        
        file_found = False
        for possible_file in possible_files:
            file_path = os.path.join(input_folder, possible_file)
            if os.path.exists(file_path):
                print(f"📄 파일 발견: {possible_file}")
                if create_hub_page(file_path, output_folder, base_url, use_html_ext):
                    print("✅ 특정 역 처리 완료")
                    sys.exit(0)
                else:
                    print("❌ 특정 역 처리 실패")
                    sys.exit(1)
                file_found = True
                break
        
        if not file_found:
            print(f"❌ {target_station}에 대한 JSON 파일을 찾을 수 없습니다.")
            sys.exit(1)
    else:
        # 모든 JSON 파일 처리
        if process_all_json_in_folder(input_folder, output_folder, base_url, use_html_ext):
            print("✅ 모든 파일 처리 완료")
            sys.exit(0)
        else:
            print("❌ 파일 처리 실패")
            sys.exit(1)


if __name__ == "__main__":
    main()
