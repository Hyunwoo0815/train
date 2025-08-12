# GitHub Actions용 열차시간표 HTML 생성기
# html_make_github.py

import os
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import time
import concurrent.futures
import hashlib
from pathlib import Path
import re
import glob

class MetaManager:
    def __init__(self, meta_file_path=None):
        # 환경변수에서 출력 디렉토리 가져오기
        output_dir = os.getenv('OUTPUT_FOLDER', '.')
        if meta_file_path is None:
            meta_file_path = os.path.join(output_dir, "meta.json")
        self.meta_file_path = meta_file_path
        self.meta_data = self.load_meta()
    
    def load_meta(self):
        """meta.json 파일 로드"""
        if os.path.exists(self.meta_file_path):
            try:
                with open(self.meta_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if "pages" not in data:
                        print(f"INFO: 'pages' 키가 없어서 추가합니다.")
                        data["pages"] = {}
                    return data
            except (json.JSONDecodeError, FileNotFoundError) as e:
                print(f"INFO: meta.json 파일을 읽을 수 없습니다: {e}. 새로 생성합니다.")
                return {"pages": {}}
        else:
            print(f"INFO: meta.json 파일이 없습니다. 새로 생성합니다: {self.meta_file_path}")
            return {"pages": {}}
    
    def save_meta(self):
        """meta.json 파일 저장"""
        try:
            if "pages" not in self.meta_data:
                self.meta_data["pages"] = {}
            
            os.makedirs(os.path.dirname(self.meta_file_path), exist_ok=True)
            
            with open(self.meta_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.meta_data, f, ensure_ascii=False, indent=2)
            print(f"INFO: meta.json 저장 완료: {self.meta_file_path}")
        except Exception as e:
            print(f"ERROR: meta.json 저장 실패: {e}")
    
    def get_or_create_page_dates(self, page_url, title=""):
        """페이지의 발행일/수정일 가져오기 또는 생성"""
        now = datetime.now()
        iso_date = now.strftime("%Y-%m-%dT%H:%M:%S+09:00")
        
        if "pages" not in self.meta_data:
            print(f"INFO: 'pages' 키가 없어서 생성합니다.")
            self.meta_data["pages"] = {}
        
        if page_url in self.meta_data["pages"]:
            # 기존 페이지 - 수정일만 업데이트
            page_info = self.meta_data["pages"][page_url]
            page_info["modified_date"] = iso_date
            page_info["version"] = page_info.get("version", 1) + 1
            
            print(f"INFO: ✅ 기존 페이지 수정: {page_url}")
            print(f"INFO:    발행일: {page_info['published_date']}")
            print(f"INFO:    수정일: {iso_date} (버전 {page_info['version']})")
            
        else:
            # 새 페이지 - 발행일과 수정일 동일하게 설정
            self.meta_data["pages"][page_url] = {
                "published_date": iso_date,
                "modified_date": iso_date,
                "title": title,
                "created_by": "github-actions",
                "version": 1
            }
            
            print(f"INFO: 🆕 새 페이지 생성: {page_url}")
            print(f"INFO:    발행일: {iso_date}")
        
        self.save_meta()
        return self.meta_data["pages"][page_url]
    
    def get_formatted_dates(self, page_url, title=""):
        """HTML에서 사용할 포맷된 날짜 반환"""
        try:
            page_info = self.get_or_create_page_dates(page_url, title)
            
            pub_date = datetime.fromisoformat(page_info["published_date"].replace("+09:00", ""))
            mod_date = datetime.fromisoformat(page_info["modified_date"].replace("+09:00", ""))
            
            return {
                "published_iso": page_info["published_date"],
                "modified_iso": page_info["modified_date"],
                "published_kr": pub_date.strftime("%Y년 %m월 %d일"),
                "modified_kr": mod_date.strftime("%Y년 %m월 %d일"),
                "published_simple": pub_date.strftime("%Y-%m-%d"),
                "modified_simple": mod_date.strftime("%Y-%m-%d"),
                "version": page_info["version"],
                "is_updated": page_info["published_date"] != page_info["modified_date"]
            }
        except Exception as e:
            print(f"ERROR: get_formatted_dates 오류: {e}")
            now = datetime.now()
            iso_date = now.strftime("%Y-%m-%dT%H:%M:%S+09:00")
            kr_date = now.strftime("%Y년 %m월 %d일")
            simple_date = now.strftime("%Y-%m-%d")
            
            return {
                "published_iso": iso_date,
                "modified_iso": iso_date,
                "published_kr": kr_date,
                "modified_kr": kr_date,
                "published_simple": simple_date,
                "modified_simple": simple_date,
                "version": 1,
                "is_updated": False
            }

# 환경변수에서 설정값 가져오기
def get_config():
    """환경변수에서 설정값 로드"""
    config = {
        'service_key': os.getenv('SERVICE_KEY', "WKp1VvR7awnciw/bWZyS/ucpv8Tiihgn8LgHK7a7Hw0u+ewXMZNo7buPDOywQc2k7pjJssVL39S0Oe6RWzCa3w=="),
        'input_folder': os.getenv('INPUT_FOLDER', 'cache'),
        'output_folder': os.getenv('OUTPUT_FOLDER', '.'),
        'station_list_path': os.getenv('STATION_LIST_PATH', 'station_list.json'),
        'site_base_url': os.getenv('SITE_BASE_URL', 'https://train.medilocator.co.kr'),
        'use_html_extension': os.getenv('USE_HTML_EXTENSION', 'false').lower() == 'true',
        'target_station': os.getenv('TARGET_STATION', ''),
        'max_days': int(os.getenv('MAX_DAYS', '7')),
        'overwrite_mode': os.getenv('OVERWRITE_MODE', 'true').lower() == 'true',
        'schedule_mode': os.getenv('SCHEDULE_MODE', 'multi').lower(),  # 🆕 추가
        'single_date': os.getenv('SINGLE_DATE', '')  # 🆕 추가 (YYYYMMDD 형식)
    }
    
    print(f"INFO: 설정 로드 완료")
    print(f"INFO: 입력 폴더: {config['input_folder']}")
    print(f"INFO: 출력 폴더: {config['output_folder']}")
    print(f"INFO: HTML 확장자: {config['use_html_extension']}")
    print(f"INFO: 대상 역: {config['target_station'] or '전체'}")
    print(f"INFO: 스케줄 모드: {config['schedule_mode']}")  # 🆕 추가
    if config['schedule_mode'] == 'multi':
        print(f"INFO: 다중 날짜: {config['max_days']}일")
    else:
        print(f"INFO: 단일 날짜: {config['single_date'] or '오늘'}")
    print(f"INFO: 덮어쓰기 모드: {config['overwrite_mode']}")
    
    return config

def format_station(name):
    """역명 포맷 함수"""
    return name if name.endswith("역") else f"{name}역"

def get_multiple_dates(days=7):
    """여러 날짜 생성"""
    dates = []
    base_date = datetime.now() + timedelta(days=1)
    
    for i in range(days):
        target_date = base_date + timedelta(days=i)
        dates.append({
            'date_str': target_date.strftime("%Y%m%d"),
            'display_date': target_date.strftime("%Y년 %m월 %d일"),
            'short_date': target_date.strftime("%m/%d"),
            'day_name': target_date.strftime("%a"),
            'is_weekend': target_date.weekday() >= 5
        })
    
    return dates

def get_available_stations(input_folder):
    """사용 가능한 출발역 목록 반환"""
    available_stations = []
    
    if os.path.exists(input_folder):
        for json_file in os.listdir(input_folder):
            if json_file.endswith(".json"):
                station_name = os.path.splitext(json_file)[0]
                available_stations.append(station_name)
    
    available_stations.sort()
    print(f"INFO: 사용 가능한 출발역 {len(available_stations)}개 발견")
    
    return available_stations

class TrainScheduleIntroGenerator:
    """인트로 자동 생성기"""
    
    def __init__(self):
        self.train_types = {
            'KTX': { 'speed': '가장 빠른', 'price': '고속' },
            'KTX-산천': { 'speed': '가장 빠른', 'price': '고속' },
            'SRT': { 'speed': '빠른', 'price': '고속' },
            'ITX-새마을': { 'speed': '준고속', 'price': '중급' },
            '무궁화호': { 'speed': '경제적인', 'price': '저렴한' }
        }

    def format_time(self, time):
        """시간을 "오전/오후 H시 M분" 형식으로 변환"""
        hour, minute = int(time[:2]), int(time[2:])
        
        if hour < 12:
            return f"오전 {hour}시 {minute:02d}분"
        elif hour == 12:
            return f"오후 12시 {minute:02d}분"
        else:
            return f"오후 {hour-12}시 {minute:02d}분"

    def find_fastest_route(self, schedule_data):
        """최단시간 열차 찾기"""
        fastest = None
        shortest_time = float('inf')

        for train in schedule_data:
            duration = self.parse_duration(train.get('duration', ''))
            if duration > 0 and duration < shortest_time:
                shortest_time = duration
                fastest = train

        return fastest

    def find_cheapest_route(self, schedule_data):
        """가장 저렴한 열차 찾기"""
        cheapest = None
        lowest_price = float('inf')

        for train in schedule_data:
            try:
                price = int(train.get('adult_charge', 0))
                if price > 0 and price < lowest_price:
                    lowest_price = price
                    cheapest = train
            except:
                continue

        if cheapest is None and schedule_data:
            cheapest = schedule_data[0]

        return cheapest

    def parse_duration(self, duration_str):
        """소요시간을 분으로 변환"""
        if not duration_str:
            return 0
        
        match = re.search(r'(\d+)시간\s*(\d+)분', duration_str)
        if match:
            hours, minutes = int(match.group(1)), int(match.group(2))
            return hours * 60 + minutes
        return 0

    def find_first_last_train(self, schedule_data):
        """첫차/막차 찾기"""
        if not schedule_data:
            return None, None
        
        sorted_trains = sorted(schedule_data, key=lambda x: x.get('departure_time', ''))
        return sorted_trains[0], sorted_trains[-1]

    def calculate_duration(self, dep_time, arr_time):
        """소요시간 계산"""
        dep_h, dep_m = int(dep_time[:2]), int(dep_time[2:])
        arr_h, arr_m = int(arr_time[:2]), int(arr_time[2:])
        
        duration = (arr_h * 60 + arr_m) - (dep_h * 60 + dep_m)
        if duration < 0:
            duration += 1440
        
        return f"{duration//60}시간 {duration%60}분"

    def generate_intro(self, from_station, to_station, schedule_data, update_date, days=7):
        """메인 인트로 생성"""
        if not schedule_data:
            return {
                'main_description': f"{from_station}에서 {to_station}까지의 열차 시간표 정보를 제공합니다.",
                'update_info': f"• 최종 갱신: {self.format_date(update_date)}\n• 매주 자동 업데이트",
                'full_intro': ""
            }

        # 각 열차에 소요시간 정보 추가
        enhanced_data = []
        for train in schedule_data:
            enhanced_train = train.copy()
            dep_time = train.get('departure_time', '')
            arr_time = train.get('arrival_time', '')
            
            if len(dep_time) >= 12 and len(arr_time) >= 12:
                dep_formatted = dep_time[8:12]
                arr_formatted = arr_time[8:12]
                duration = self.calculate_duration(dep_formatted, arr_formatted)
                enhanced_train['duration'] = duration
            
            enhanced_data.append(enhanced_train)

        fastest = self.find_fastest_route(enhanced_data)
        cheapest = self.find_cheapest_route(enhanced_data)
        first_train, last_train = self.find_first_last_train(enhanced_data)

        if not fastest or not first_train or not last_train:
            if enhanced_data:
                fastest = enhanced_data[0] if not fastest else fastest
                cheapest = enhanced_data[0] if not cheapest else cheapest
                first_train = enhanced_data[0] if not first_train else first_train
                last_train = enhanced_data[-1] if not last_train else last_train
            else:
                return {
                    'main_description': f"{from_station}에서 {to_station}까지의 열차 시간표 정보를 제공합니다.",
                    'update_info': f"• 최종 갱신: {self.format_date(update_date)}\n• 매주 자동 업데이트",
                    'full_intro': ""
                }

        # 시간 포맷팅
        first_dep = first_train.get('departure_time', '')[8:12] if len(first_train.get('departure_time', '')) >= 12 else ''
        last_dep = last_train.get('departure_time', '')[8:12] if len(last_train.get('departure_time', '')) >= 12 else ''

        first_time = self.format_time(first_dep) if first_dep else '정보없음'
        last_time = self.format_time(last_dep) if last_dep else '정보없음'

        fastest_duration = fastest.get('duration', '정보없음')
        
        cheapest_price_str = "요금확인필요"
        
        try:
            cheapest_price = int(cheapest.get('adult_charge', 0))
            if cheapest_price > 0:
                cheapest_price_str = f"{cheapest_price:,}원"
        except:
            cheapest_price_str = "요금확인필요"

        # 메인 설명 생성
        if fastest.get('train_type') == cheapest.get('train_type'):
            if cheapest_price_str == "요금확인필요":
                main_description = f"{from_station}에서 {to_station}로 가실 때 {fastest.get('train_type')}를 이용하면 {fastest_duration}이 걸립니다. 요금은 예매 시 확인 가능하며, {first_time} 첫차부터 {last_time} 막차까지 "
            else:
                main_description = f"{from_station}에서 {to_station}로 가실 때 {fastest.get('train_type')}를 이용하면 {fastest_duration}이 걸리며, 가장 합리적인 {cheapest_price_str}부터 이용하실 수 있습니다. {first_time} 첫차부터 {last_time} 막차까지 "
        else:
            if cheapest_price_str == "요금확인필요":
                main_description = f"{from_station}에서 {to_station}로 가실 때 가장 빠른 방법은 {fastest.get('train_type')} 이용하는 것이며, {fastest_duration}이 소요됩니다. 요금은 예매 시 확인 가능하며, {first_time} 첫차를 시작으로 {last_time} 막차까지 "
            else:
                main_description = f"{from_station}에서 {to_station}로 가실 때 가장 빠른 방법은 {fastest.get('train_type')} 이용하는 것이며, {fastest_duration}이 소요 됩니다. 가장 경제적인 {cheapest.get('train_type')}는 {cheapest_price_str}부터 합리적인 가격에 이용하실 수 있습니다. {first_time} 첫차를 시작으로 {last_time} 막차까지 "

        # 날짜 범위 계산
        start_date = datetime.strptime(update_date, '%Y-%m-%d')
        end_date = start_date + timedelta(days=days-1)
        date_range = f"{self.format_date_short(start_date)}~{self.format_date_short(end_date)}"

        # 업데이트 정보
        update_info = f"""**📅 업데이트 정보**  
- 최종 갱신: {self.format_date(update_date)}  
- 제공 기간: {days}일간 ({date_range})  
- 갱신 주기: 매주 월요일 자동 업데이트  
- 데이터 출처: 코레일 공식 시간표"""

        return {
            'main_description': main_description,
            'update_info': update_info,
            'full_intro': f"{main_description}\n\n{update_info}"
        }
    
    def format_date(self, date_str):
        """날짜 포맷팅 (전체)"""
        date = datetime.strptime(date_str, '%Y-%m-%d')
        return f"{date.year}년 {date.month:02d}월 {date.day:02d}일"

    def format_date_short(self, date):
        """날짜 포맷팅 (짧은 형식)"""
        return f"{date.month:02d}/{date.day:02d}"

class TrainScheduleGenerator:
    """열차 시간표 생성기"""
    
    def __init__(self, config):
        self.config = config
        self.cache_dir = Path("api_cache")
        self.cache_dir.mkdir(exist_ok=True)
        self.intro_generator = TrainScheduleIntroGenerator()
        
        # 역 정보 로드
        try:
            with open(config['station_list_path'], "r", encoding="utf-8") as f:
                self.station_ids = json.load(f)
            print(f"INFO: 역 정보 로드 완료: {len(self.station_ids)}개 역")
        except Exception as e:
            print(f"ERROR: 역 정보 로드 실패: {e}")
            self.station_ids = {}
            
    def generate_url_slug(self, from_station, to_station):
        """SEO 친화적 URL 슬러그 생성"""
        slug = f"{from_station}에서-{to_station}-가는-열차시간표"
        if self.config['use_html_extension']:
            slug += ".html"
        return slug
            
    def generate_filename(self, from_station, to_station):
        """파일명 생성"""
        filename = f"{from_station}에서-{to_station}-가는-열차시간표"
        if self.config['use_html_extension']:
            filename += ".html"
        return filename
    
    def fetch_train_data(self, from_id, to_id, date_str):
        """열차 데이터 수집"""
        
        cache_key = f"{from_id}_{to_id}_{date_str}"
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        # 캐시가 6시간 이내면 사용
        if cache_file.exists():
            file_age = time.time() - cache_file.stat().st_mtime
            if file_age < (6 * 3600):
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except:
                    pass
        
        # API 호출
        url = "http://apis.data.go.kr/1613000/TrainInfoService/getStrtpntAlocFndTrainInfo"
        params = {
            "serviceKey": self.config['service_key'],
            "depPlaceId": from_id,
            "arrPlaceId": to_id,
            "depPlandTime": date_str,
            "numOfRows": "100",
            "pageNo": "1",
            "_type": "xml"
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            root = ET.fromstring(response.content)
            
            result_code = root.findtext(".//resultCode")
            if result_code != "00":
                return []
            
            items = root.findall(".//item")
            train_data = []
            
            for item in items:
                train_info = {
                    'departure_time': item.findtext("depplandtime"),
                    'arrival_time': item.findtext("arrplandtime"),
                    'train_type': item.findtext("traingradename"),
                    'train_number': item.findtext("trainno"),
                    'adult_charge': item.findtext("adultcharge"),
                    'dep_station': item.findtext("depplacename"),
                    'arr_station': item.findtext("arrplacename")
                }
                train_data.append(train_info)
            
            # 캐시 저장
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(train_data, f, ensure_ascii=False, indent=2)
            
            return train_data
            
        except Exception as e:
            print(f"ERROR: API 호출 실패: {e}")
            return []
    
    def generate_internal_links(self, station_name, max_links=6):
        """내부링크 HTML 생성"""
        
        json_file = os.path.join(self.config['input_folder'], f"{station_name}.json")
        
        if not os.path.exists(json_file):
            return f"<!-- {station_name}.json 파일을 찾을 수 없습니다 -->"
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            departure = format_station(station_name)
            destinations = data.get('도착지', [])
            
            if not destinations:
                return "<!-- 관련 노선 정보가 없습니다 -->"
            
            import random
            shuffled_destinations = destinations.copy()
            random.shuffle(shuffled_destinations)
            selected_destinations = shuffled_destinations[:max_links]
            
            html = []
            html.append('<h2>🚇 관련 노선</h2>')
            html.append('<div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0;">')
            html.append('<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px;">')
            
            for dest in selected_destinations:
                destination = format_station(dest)
                url_slug = self.generate_url_slug(departure, destination)
                
                link_html = f"""
                <a href="/{url_slug}" 
                style="padding: 12px; background: white; border-radius: 6px; text-decoration: none; 
                        border: 1px solid #e9ecef; text-align: center; display: block; 
                        transition: all 0.3s ease; box-shadow: 0 2px 4px rgba(0,0,0,0.1);"
                onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 4px 8px rgba(0,0,0,0.15)';"
                onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 2px 4px rgba(0,0,0,0.1)';"
                title="{departure}에서 {destination} 가는 열차시간표 바로가기">
                    <strong style="color: #2563eb; font-size: 14px;">{departure} → {destination}</strong><br>
                    <small style="color: #6c757d; font-size: 12px;">열차시간표 바로가기</small>
                </a>
                """
                html.append(link_html.strip())
            
            html.append('</div>')
            html.append('<div style="margin-top: 15px; padding: 10px; background: rgba(37, 99, 235, 0.1); border-radius: 6px;">')
            html.append(f'<p style="margin: 0; font-size: 13px; color: #4b5563; text-align: center;">')
            html.append(f'💡 <strong>{departure}</strong>에서 출발하는 다른 노선도 확인해보세요!')
            html.append('</p>')
            html.append('</div>')
            html.append('</div>')
            
            return '\n'.join(html)
            
        except Exception as e:
            print(f"ERROR: 내부링크 생성 실패: {e}")
            return f"<!-- 내부링크 생성 오류: {e} -->"

    def generate_multi_date_html(self, from_station, to_station, combined_trains, train_types_str, days, all_date_data, valid_dates):
        """다중 날짜 HTML 생성"""
        
        url_slug = self.generate_url_slug(from_station, to_station)
        page_url = f"/{url_slug}"
        page_title = f"{from_station}에서 {to_station} 가는 열차시간표 | 첫차 막차 요금 소요시간 안내"
        
        # 메타 매니저 초기화 및 날짜 정보 가져오기
        meta_manager = MetaManager()
        dates = meta_manager.get_formatted_dates(page_url, page_title)

        # 인트로 생성
        intro_data = self.intro_generator.generate_intro(
            from_station, to_station, combined_trains, 
            datetime.now().strftime('%Y-%m-%d'), days
        )
        
        # 전체 통계 계산
        all_dep_times = []
        all_prices = []
        total_trains = len(combined_trains)
        avg_trains = round(total_trains / 7) if days >= 7 else round(total_trains / days)
        
        for train in combined_trains:
            if not train.get('departure_time') or not train.get('arrival_time'):
                continue
                
            dep_time = train['departure_time'][8:12]
            all_dep_times.append(dep_time)
            
            try:
                price = int(train['adult_charge']) if train.get('adult_charge') else 0
                if price > 0:
                    all_prices.append(price)
            except:
                pass
        
        first_train = f"{min(all_dep_times)[:2]}:{min(all_dep_times)[2:]}" if all_dep_times else "정보없음"
        last_train = f"{max(all_dep_times)[:2]}:{max(all_dep_times)[2:]}" if all_dep_times else "정보없음"
        min_price = f"{min(all_prices):,}원" if all_prices else "요금확인필요"
        max_price = f"{max(all_prices):,}원" if all_prices else "요금확인필요"
        
        # URL 설정
        canonical_url = f"{self.config['site_base_url']}/{url_slug}"
        reverse_url_slug = self.generate_url_slug(to_station, from_station)
        reverse_url = f"{self.config['site_base_url']}/{reverse_url_slug}"
        
        # 탭 버튼 생성
        tab_buttons_html = ""
        for i, date_str in enumerate(valid_dates):
            date_info = all_date_data[date_str]['date_info']
            active_class = "active" if i == 0 else ""
            weekend_class = "weekend" if date_info['is_weekend'] else ""
            
            tab_buttons_html += f"""
            <button class="tab-button {active_class} {weekend_class}" 
                    onclick="showDate('{date_str}')" 
                    role="tab" 
                    aria-selected="{'true' if i == 0 else 'false'}" 
                    aria-controls="date-{date_str}"
                    data-date="{date_str}"
                    id="tab-{date_str}">
                {date_info['short_date']}<br><small>{date_info['day_name']}</small>
            </button>
            """
        
        # 날짜별 콘텐츠 생성
        date_contents_html = ""
        for i, date_str in enumerate(valid_dates):
            date_data = all_date_data[date_str]
            date_info = date_data['date_info']
            date_trains = date_data['trains']
            
            active_style = "" if i == 0 else "style='display:none;'"
            active_class = "active" if i == 0 else ""
            
            # 해당 날짜의 열차들을 그룹핑
            train_groups = {
                'KTX': [],
                'SRT': [],
                'ITX': [],
                '무궁화호': []
            }
            
            for train in date_trains:
                if not train.get('departure_time') or not train.get('arrival_time'):
                    continue
                    
                dep_time = train['departure_time'][8:12]
                arr_time = train['arrival_time'][8:12]
                train_type = train['train_type']
                
                # 소요시간 계산
                dep_h, dep_m = int(dep_time[:2]), int(dep_time[2:])
                arr_h, arr_m = int(arr_time[:2]), int(arr_time[2:])
                duration = (arr_h * 60 + arr_m) - (dep_h * 60 + dep_m)
                if duration < 0:
                    duration += 1440
                
                try:
                    price = int(train['adult_charge']) if train.get('adult_charge') else 0
                    formatted_price = f"{price:,}원" if price > 0 else "요금 확인 필요"
                except:
                    formatted_price = "요금 확인 필요"
                
                train_info = {
                    'type': train_type,
                    'dep_time': dep_time,
                    'arr_time': arr_time,
                    'duration': f"{duration//60}시간 {duration%60}분",
                    'price': formatted_price,
                    'number': train.get('train_number', '')
                }
                
                # 그룹별 분류
                if "KTX" in train_type:
                    train_groups['KTX'].append(train_info)
                elif "SRT" in train_type:
                    train_groups['SRT'].append(train_info)
                elif "새마을" in train_type or "ITX" in train_type or "마음" in train_type:
                    train_groups['ITX'].append(train_info)
                elif "무궁화" in train_type:
                    train_groups['무궁화호'].append(train_info)
            
            # 해당 날짜의 열차 카드 HTML 생성
            date_trains_html = ""
            
            # 고속열차
            if train_groups['KTX'] or train_groups['SRT']:
                date_trains_html += "<h3>🚄 고속열차</h3>"
                
                for train in train_groups['KTX'] + train_groups['SRT']:
                    date_trains_html += f"""
                    <div class='train-card' data-train-type='{train['type']}'>
                        <span class='badge'>{train['type']}</span>
                        <p class='highlight'>⏰ 출발 {train['dep_time'][:2]}:{train['dep_time'][2:]} → 도착 {train['arr_time'][:2]}:{train['arr_time'][2:]}</p>
                        <p>🕓 소요시간: {train['duration']} | 💰 요금: {train['price']}</p>
                        <div class='button-group'>
                            <a class='btn-left seat' href='https://www.korail.com/ticket/main' rel='noopener noreferrer' aria-label="좌석 조회">💺 좌석 조회</a>
                            <a class='btn-right reserve' href='https://www.korail.com/ticket/main' rel='noopener noreferrer' aria-label="예매하러 가기">🎫 예매하러 가기</a>
                            <a class='btn-left stops' href='https://www.korail.com/ticket/main' rel='noopener noreferrer' aria-label="경유지 조회">🛤 경유지 조회</a>
                            <a class='btn-right reverse' href='{reverse_url}' aria-label="왕복 시간표 보기">🔁 왕복 시간표</a>
                        </div>
                    </div>
                    """
            
            # 일반열차
            if train_groups['ITX'] or train_groups['무궁화호']:
                date_trains_html += "<h3>🚆 일반열차</h3>"
                
                for train in train_groups['ITX'] + train_groups['무궁화호']:
                    date_trains_html += f"""
                    <div class='train-card' data-train-type='{train['type']}'>
                        <span class='badge'>{train['type']}</span>
                        <p class='highlight'>⏰ 출발 {train['dep_time'][:2]}:{train['dep_time'][2:]} → 도착 {train['arr_time'][:2]}:{train['arr_time'][2:]}</p>
                        <p>🕓 소요시간: {train['duration']} | 💰 요금: {train['price']}</p>
                        <div class='button-group'>
                            <a class='btn-left seat' href='https://www.korail.com/ticket/main' rel='noopener noreferrer'>💺 좌석 조회</a>
                            <a class='btn-right reserve' href='https://www.korail.com/ticket/main' rel='noopener noreferrer'>🎫 예매하러 가기</a>
                            <a class='btn-left stops' href='https://www.korail.com/ticket/main' rel='noopener noreferrer'>🛤 경유지 조회</a>
                            <a class='btn-right reverse' href='{reverse_url}'>🔁 왕복 시간표</a>
                        </div>
                    </div>
                    """
            
            date_contents_html += f"""
            <div id="date-{date_str}" class="date-content {active_class}" role="tabpanel" aria-labelledby="tab-{date_str}" {active_style}>
                <div class="date-header">
                    <h2>📅 {date_info['display_date']} ({date_info['day_name']})</h2>
                    <p class="train-count">총 {len(date_trains)}개 열차 운행</p>
                </div>
                {date_trains_html}
            </div>
            """
        
        # 내부 링크 생성
        station_name_for_cache = from_station.replace("역", "")
        internal_links_html = self.generate_internal_links(station_name_for_cache, max_links=6)
        
        # 설명 생성
        description = f"{from_station}에서 {to_station} 가는 열차시간표 입니다. "
        description += f"해당 노선은 일 평균 {avg_trains}회 운행하고 있으며 첫차 : {first_train}, 막차 : {last_train} 입니다. 열차요금은 최저{min_price} 최고{max_price} 입니다. "
        description += f"시간표 업데이트 : {dates['modified_simple']}"
        
        # 사용자 표시용 날짜 정보
        update_badge = ""
        if dates['is_updated']:
            update_badge = f"<span style='background: #28a745; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-left: 8px;'>업데이트됨</span>"
        
        article_meta = f"""
        <div class="article-meta" style="text-align: center; margin-bottom: 20px; font-size: 14px; color: #6c757d;">
            <time datetime="{dates['published_iso']}" itemprop="datePublished">
                📅 발행일: {dates['published_kr']}
            </time>
            <span style="margin: 0 8px;">|</span>
            <time datetime="{dates['modified_iso']}" itemprop="dateModified">  
                🔄 최종 수정: {dates['modified_kr']}
            </time>
            {update_badge}
            <small style="display: block; margin-top: 4px; opacity: 0.7;">v{dates['version']}</small>
        </div>
        """
        
        # CSS 및 JavaScript는 원본과 동일하게 유지 (길어서 생략)
        css = """<style>
        /* CSS 코드는 원본과 동일 */
        :root {
            --primary-color: #0056b3;
            --secondary-color: #007bff;
            --accent-color: #ffcc00;
            --success-color: #28a745;
            --warning-color: #ffc107;
            --danger-color: #dc3545;
            --light-bg: #f8f9fa;
            --white: #ffffff;
            --gray-100: #f8f9fa;
            --gray-200: #e9ecef;
            --gray-600: #6c757d;
            --gray-800: #495057;
            --text-dark: #212529;
            --border-radius: 12px;
            --box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            --gradient-primary: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            --gradient-accent: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }

        * { box-sizing: border-box; }

        body { 
            font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
            background: var(--gradient-primary);
            margin: 0; 
            padding: 20px 10px; 
            line-height: 1.6; 
            color: var(--text-dark);
            min-height: 100vh;
        }

        .container { 
            max-width: 480px; 
            margin: 0 auto; 
            padding: 24px; 
            background: var(--white); 
            border-radius: 20px; 
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            position: relative;
            overflow: hidden;
            animation: slideUp 0.6s ease-out;
        }

        @keyframes slideUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }

        h1 { 
            font-size: 26px; 
            color: var(--primary-color); 
            text-align: center; 
            margin-bottom: 24px; 
            font-weight: 700;
            line-height: 1.3;
        }

        h2 { 
            font-size: 20px; 
            color: var(--primary-color); 
            margin: 32px 0 16px 0; 
            padding-bottom: 8px; 
            border-bottom: 2px solid var(--gray-200); 
            font-weight: 600;
        }

        h3 { 
            font-size: 16px; 
            color: var(--gray-800); 
            margin: 24px 0 12px 0; 
            background: var(--light-bg); 
            padding: 12px 16px; 
            border-radius: var(--border-radius); 
            border-left: 4px solid var(--secondary-color);
            font-weight: 600;
        }

        .intro-section { 
            background: var(--gradient-primary); 
            color: var(--white); 
            padding: 24px; 
            border-radius: 16px; 
            margin: 20px 0; 
            line-height: 1.7;
            box-shadow: var(--box-shadow);
        }

        .summary-stats { 
            background: linear-gradient(135deg, #e3f2fd 0%, #f3e5f5 100%); 
            padding: 20px; 
            border-radius: var(--border-radius); 
            margin: 20px 0;
            border: 1px solid #bbdefb;
        }

        .summary-stats p { 
            margin: 8px 0; 
            font-size: 14px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .tab-navigation {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin: 24px 0;
            padding: 16px;
            background: var(--light-bg);
            border-radius: 16px;
            border: 1px solid var(--gray-200);
        }
        
        .tab-button {
            flex: 1;
            min-width: 60px;
            padding: 12px 8px;
            background: var(--white);
            border: 2px solid var(--gray-200);
            border-radius: 10px;
            cursor: pointer;
            transition: var(--transition);
            text-align: center;
            font-size: 13px;
            font-weight: 600;
            touch-action: manipulation;
            user-select: none;
        }
        
        .tab-button.active {
            background: var(--secondary-color);
            color: var(--white);
            border-color: var(--secondary-color);
            transform: translateY(-2px) scale(1.02);
            box-shadow: 0 6px 16px rgba(0,123,255,0.3);
        }
        
        .tab-button.weekend {
            background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
            border-color: #ffeaa7;
        }
        
        .tab-button.weekend.active {
            background: linear-gradient(135deg, #e17055 0%, #d63031 100%);
            border-color: #e17055;
        }

        .date-content {
            animation: fadeIn 0.5s ease-in-out;
            min-height: 200px;
        }
        
        .date-header {
            text-align: center;
            margin-bottom: 24px;
            padding: 16px;
            background: linear-gradient(135deg, var(--light-bg) 0%, #e9ecef 100%);
            border-radius: var(--border-radius);
        }
        
        .train-count {
            color: var(--gray-600);
            font-size: 14px;
            margin: 8px 0;
            font-weight: 500;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .train-card { 
            background: var(--white); 
            border-left: 6px solid var(--secondary-color); 
            border-radius: var(--border-radius); 
            padding: 20px; 
            margin-bottom: 16px; 
            box-shadow: var(--box-shadow);
            transition: var(--transition);
        }

        .train-card:hover {
            transform: translateY(-4px) scale(1.01);
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
        }

        .badge { 
            background: linear-gradient(135deg, var(--accent-color), #ffd700);
            color: #222; 
            font-size: 12px; 
            font-weight: bold; 
            padding: 6px 12px; 
            border-radius: 20px; 
            display: inline-block; 
            margin-bottom: 12px;
        }

        .highlight { 
            font-size: 18px; 
            font-weight: 600; 
            color: var(--text-dark); 
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .train-card p { 
            margin: 6px 0; 
            font-size: 15px; 
            color: var(--gray-600);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .button-group { 
            display: grid; 
            grid-template-columns: 1fr 1fr; 
            gap: 10px; 
            margin-top: 20px; 
            padding-top: 20px; 
            border-top: 1px solid var(--gray-200); 
        }

        .btn-left, .btn-right { 
            padding: 12px 16px; 
            font-size: 13px; 
            font-weight: 600; 
            border-radius: var(--border-radius); 
            text-decoration: none; 
            text-align: center; 
            transition: var(--transition); 
            border: none; 
            cursor: pointer;
            box-shadow: var(--box-shadow);
        }

        .btn-left.seat { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: var(--white); }
        .btn-right.reserve { background: var(--gradient-accent); color: var(--white); }
        .btn-left.stops { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: var(--white); }
        .btn-right.reverse { background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); color: var(--white); }

        .btn-left:hover, .btn-right:hover { 
            transform: translateY(-3px) scale(1.02); 
            box-shadow: 0 8px 20px rgba(0,0,0,0.2); 
        }

        .guide-section {
            background: linear-gradient(135deg, var(--light-bg) 0%, #f0f4f8 100%);
            padding: 16px 20px;
            border-radius: var(--border-radius);
            margin-bottom: 16px;
            font-size: 14px;
            color: var(--gray-600);
            border: 1px solid var(--gray-200);
        }

        .guide-section p {
            margin: 8px 0;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        @media (max-width: 480px) { 
            body { padding: 10px 5px; }
            .container { padding: 16px; border-radius: 16px; }
            h1 { font-size: 22px; }
            .tab-navigation { gap: 4px; padding: 12px; }
            .tab-button { min-width: 50px; padding: 10px 6px; font-size: 12px; }
            .button-group { grid-template-columns: 1fr; gap: 8px; }
        }
        </style>"""

        javascript = """
        <script>
            function showDate(dateStr) {
                // 모든 탭 콘텐츠 숨기기
                document.querySelectorAll('.date-content').forEach(el => {
                    el.style.display = 'none';
                    el.classList.remove('active');
                });
                
                // 모든 탭 버튼 비활성화
                document.querySelectorAll('.tab-button').forEach(btn => {
                    btn.classList.remove('active');
                });
                
                // 클릭된 버튼 활성화
                if (event && event.target) {
                    event.target.classList.add('active');
                }
                
                // 선택된 날짜 콘텐츠 보이기
                const selectedContent = document.getElementById('date-' + dateStr);
                if (selectedContent) {
                    selectedContent.style.display = 'block';
                    selectedContent.classList.add('active');
                }
            }
            
            // 페이지 로드 시 첫 번째 탭 활성화
            document.addEventListener('DOMContentLoaded', function() {
                const firstTab = document.querySelector('.tab-button');
                if (firstTab) {
                    const dateStr = firstTab.getAttribute('data-date');
                    if (dateStr) {
                        window.event = { target: firstTab };
                        showDate(dateStr);
                    }
                }
            });
        </script>
        """
        
        # 구조화된 데이터
        structured_data = f"""
        <script type="application/ld+json">
        {{
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": "{page_title}",
            "description": "{description}",
            "url": "{canonical_url}",
            "datePublished": "{dates['published_iso']}",
            "dateModified": "{dates['modified_iso']}",
            "version": "{dates['version']}",
            "author": {{
                "@type": "Organization",
                "name": "레일가이드"
            }},
            "publisher": {{
                "@type": "Organization",
                "name": "레일가이드",
                "url": "{self.config['site_base_url']}"
            }}
        }}
        </script>
        """

        # 최종 HTML 생성
        html = f"""<!DOCTYPE html>
        <html lang='ko'>
        <head>
            <title>{page_title}</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta name="description" content="{description}">
            <meta name="keywords" content="열차시간표,기차시간표,{from_station},{to_station},{train_types_str},첫차,막차,요금,예매">
            <meta name="author" content="레일가이드">
            <meta name="robots" content="index,follow">
            
            <meta name="article:published_time" content="{dates['published_iso']}">
            <meta name="article:modified_time" content="{dates['modified_iso']}">
            <meta name="date" content="{dates['published_simple']}">

            <link rel="preconnect" href="https://www.korail.com">
            <link rel="preload" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700&display=swap" as="style">
            <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700&display=swap" rel="stylesheet">

            <meta property="og:title" content="{page_title}">
            <meta property="og:description" content="{description}">
            <meta property="og:type" content="website">
            <meta property="og:url" content="{canonical_url}">
            <meta property="og:locale" content="ko_KR">
            <meta property="og:site_name" content="레일가이드">

            <meta name="twitter:card" content="summary_large_image">
            <meta name="twitter:title" content="{page_title}">
            <meta name="twitter:description" content="{description}">

            {structured_data}

            <link rel="canonical" href="{canonical_url}">
            <meta name="theme-color" content="#0056b3">
            
            {css}
        </head>
        <body>
            <div class='container'>
                <header>
                    <h1>{from_station}에서 {to_station} 가는 열차시간표</h1>
                    {article_meta}
                </header>
                
                <main>
                    <section>
                        <h2>📋 시간표 요약 정보</h2>
                        <div class="intro-section">
                            <div>{intro_data['main_description']} 일 평균 {avg_trains}회 운행됩니다.</div>
                        </div>
                        
                        <div class="summary-stats">
                            <p><span>🚂</span> <strong>주간 평균운행 횟수:</strong> {avg_trains}회</p>
                            <p><span>⏰</span> <strong>운행 시간:</strong> 첫차 {first_train} ~ 막차 {last_train}</p>
                            <p><span>💰</span> <strong>요금 범위:</strong> {min_price} ~ {max_price}</p>
                        </div>
                    </section>

                    <nav class="tab-navigation">
                        {tab_buttons_html}
                    </nav>

                    <section>
                        {date_contents_html}
                    </section>

                    <section>
                        {internal_links_html}
                    </section>

                    <section>
                        <h2>💡 이용 안내</h2>
                        
                        <h3>🎫 예매 및 좌석 조회</h3>
                        <div class="guide-section">
                            <p>📱 <strong>온라인 예매:</strong> 코레일 홈페이지 또는 앱</p>
                            <p>📞 <strong>전화 예매:</strong> <a href="tel:1544-7788">1544-7788</a></p>
                            <p>🏢 <strong>현장 구매:</strong> 역 매표소 또는 자동발매기</p>
                            <p>💳 <strong>결제 방법:</strong> 신용카드, 체크카드, 현금, 교통카드</p>
                        </div>

                        <h3>⚠️ 이용 시 주의사항</h3>
                        <div class="guide-section">
                            <p>🕐 <strong>탑승 시간:</strong> 출발 5분 전까지 승강장 도착 권장</p>
                            <p>🎫 <strong>승차권 확인:</strong> 탑승 전 승차권과 신분증 준비</p>
                            <p>🔄 <strong>환불/변경:</strong> 출발 20분 전까지 가능 (수수료 적용)</p>
                            <p>📅 <strong>시간표 변경:</strong> 날씨나 운행 상황에 따라 변경될 수 있음</p>
                        </div>

                        <h3>💰 할인 혜택</h3>
                        <div class="guide-section">
                            <p>👴 <strong>경로우대:</strong> 만 65세 이상 30% 할인</p>
                            <p>🎓 <strong>학생할인:</strong> 중고등학생 20% 할인</p>
                            <p>👨‍👩‍👧‍👦 <strong>가족할인:</strong> 4인 이상 가족 여행시 할인</p>
                            <p>🎫 <strong>정기권:</strong> 자주 이용하는 구간은 정기권 이용</p>
                        </div>
                    </section>
                </main>

                <footer>
                    <p style='text-align:center; font-size:12px; color:var(--gray-600); margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--gray-200);'>
                        최초 생성일: {dates['published_kr']} / 최종 수정일: {dates['modified_kr']}<br>
                        <small>시간표는 실시간으로 변경될 수 있으니 예매 전 재확인 바랍니다.</small>
                    </p>
                </footer>
            </div>

            {javascript}
        </body>
        </html>"""
        
        return html

    def process_multi_date_route(self, from_station, to_station, from_station_id, to_station_id, days):
        """다중 날짜 노선 처리"""
        
        print(f"INFO: 다중날짜 처리 시작 - {from_station} → {to_station} ({days}일)")
        
        # 여러 날짜 정보 생성
        dates_info = get_multiple_dates(days)
        
        # 각 날짜별 데이터 수집
        all_date_data = {}
        total_trains = 0
        
        for date_info in dates_info:
            date_str = date_info['date_str']
            
            train_data = self.fetch_train_data(from_station_id, to_station_id, date_str)
            all_date_data[date_str] = {
                'date_info': date_info,
                'trains': train_data
            }
            
            total_trains += len(train_data)
            print(f"INFO: {date_info['short_date']} - {len(train_data)}개 열차")
            
            # API 호출 간격
            time.sleep(0.2)
        
        print(f"INFO: 전체 데이터 수집 완료 - 총 {total_trains}개 열차")
        
        # 유효한 데이터가 있는 날짜 확인
        valid_dates = []
        for date_str, data in all_date_data.items():
            if len(data['trains']) >= 1:
                valid_dates.append(date_str)
        
        if not valid_dates:
            print(f"WARNING: 유효한 데이터가 없음")
            return False
        
        # 모든 유효한 날짜의 데이터를 합치기
        combined_trains = []
        sample_date_for_types = valid_dates[0]
        
        for date_str in valid_dates:
            date_data = all_date_data[date_str]
            date_info = date_data['date_info']
            date_trains = date_data['trains']
            
            for train in date_trains:
                if not train.get('departure_time') or not train.get('arrival_time'):
                    continue
                    
                train_with_date = train.copy()
                train_with_date['travel_date'] = date_info['display_date']
                train_with_date['travel_date_short'] = date_info['short_date']
                train_with_date['day_name'] = date_info['day_name']
                train_with_date['is_weekend'] = date_info['is_weekend']
                train_with_date['date_str'] = date_str
                
                combined_trains.append(train_with_date)
        
        if len(combined_trains) < 1:
            print(f"WARNING: 전체 데이터 부족 ({len(combined_trains)}개)")
            return False
        
        # 열차 종류 파악
        sample_trains = all_date_data[sample_date_for_types]['trains']
        
        train_types = set()
        for train in sample_trains:
            train_type = train.get('train_type')
            if not train_type:
                continue
                
            if "무궁화" in train_type: 
                train_types.add("무궁화호")
            if "새마을" in train_type: 
                train_types.add("새마을호")
            if "KTX" in train_type: 
                train_types.add("KTX")
            if "SRT" in train_type: 
                train_types.add("SRT")
            if "마음" in train_type or "ITX" in train_type: 
                train_types.add("ITX")
            if "누리로" in train_type: 
                train_types.add("누리로")
        
        train_types_str = " ".join(sorted(train_types))
        
        # HTML 생성
        html = self.generate_multi_date_html(
            from_station, to_station, combined_trains, train_types_str, 
            days, all_date_data, valid_dates
        )
        
        if html:
            # 파일 저장
            filename = self.generate_filename(from_station, to_station)
            full_path = os.path.join(self.config['output_folder'], filename)
            
            try:
                os.makedirs(self.config['output_folder'], exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"INFO: ✅ 파일 저장 완료 - {filename}")
                return True
            except Exception as e:
                print(f"ERROR: 파일 저장 실패 - {e}")
                return False
        else:
            print(f"ERROR: HTML 생성 실패")
            return False

    def process_station(self, station_name):
        """특정 출발역 처리 (GitHub Actions용)"""
        
        print(f"\nINFO: 🚉 {station_name} 처리 시작...")
        
        from_station = format_station(station_name)
        from_station_id = self.station_ids.get(station_name)
        
        if not from_station_id:
            print(f"ERROR: 역 ID를 찾을 수 없습니다: {station_name}")
            return 0
        
        # 도착지 정보 로드
        json_file_path = os.path.join(self.config['input_folder'], f"{station_name}.json")
        if not os.path.exists(json_file_path):
            print(f"ERROR: 도착지 정보 파일이 없습니다: {json_file_path}")
            return 0
        
        with open(json_file_path, "r", encoding="utf-8") as f:
            route_data = json.load(f)
        arrival_list = route_data.get("도착지", [])
        
        print(f"INFO: 📍 {len(arrival_list)}개 도착지 발견")
        
        generated_count = 0
        
        for i, to_station_raw in enumerate(arrival_list, 1):
            to_station = format_station(to_station_raw)
            to_station_id = self.station_ids.get(to_station_raw)
            
            if not to_station_id:
                continue
            
            print(f"INFO: [{i:2d}/{len(arrival_list)}] {from_station} → {to_station} ", end="")
            
            try:
                # GitHub Actions에서는 항상 다중 날짜 모드
                success = self.process_multi_date_route(
                    from_station, to_station, from_station_id, to_station_id, 
                    self.config['max_days']
                )
                
                if success:
                    generated_count += 1
                    print("✅")
                else:
                    print("⚠ (데이터 부족)")
                    
            except Exception as e:
                print(f"❌ {e}")
            
            time.sleep(0.1)  # API 호출 간격
        
        print(f"INFO: 🎉 {generated_count}개 페이지 생성 완료")
        return generated_count

def main():
    """GitHub Actions용 메인 실행 함수"""
    
    try:
        # 설정 로드
        config = get_config()
        
        # 생성기 초기화
        generator = TrainScheduleGenerator(config)
        
        # 사용 가능한 출발역 목록 가져오기
        available_stations = get_available_stations(config['input_folder'])
        
        if not available_stations:
            print("ERROR: 사용 가능한 출발역이 없습니다.")
            return
        
        # 처리할 출발역 결정
        if config['target_station']:
            # 특정 역만 처리
            if config['target_station'] in available_stations:
                selected_stations = [config['target_station']]
                print(f"INFO: 특정 역 처리 모드: {config['target_station']}")
            else:
                print(f"ERROR: 지정된 역을 찾을 수 없습니다: {config['target_station']}")
                print(f"INFO: 사용 가능한 역: {', '.join(available_stations[:10])}...")
                return
        else:
            # 모든 역 처리
            selected_stations = available_stations
            print(f"INFO: 전체 역 처리 모드: {len(selected_stations)}개 역")
        
        # 처리 시작
        total_generated = 0
        start_time = time.time()
        
        print(f"\nINFO: 🚀 처리 시작!")
        print(f"INFO: 📋 출발역: {len(selected_stations)}개")
        print(f"INFO: ⚙️ 다중 날짜 모드 ({config['max_days']}일)")
        print(f"INFO: 📁 출력 폴더: {config['output_folder']}")
        print(f"INFO: 🌐 기본 URL: {config['site_base_url']}")
        print("=" * 50)
        
        # 기존 HTML 파일 정리 (덮어쓰기 모드가 아닌 경우)
        if not config['overwrite_mode']:
            print("INFO: 🧹 기존 HTML 파일 정리 중...")
            pattern = os.path.join(config['output_folder'], "*열차시간표*")
            existing_files = glob.glob(pattern)
            for file_path in existing_files:
                try:
                    os.remove(file_path)
                    print(f"INFO: 삭제됨 - {os.path.basename(file_path)}")
                except Exception as e:
                    print(f"WARNING: 삭제 실패 - {os.path.basename(file_path)}: {e}")
        
        # 각 출발역 처리
        for i, station in enumerate(selected_stations, 1):
            print(f"\nINFO: 📍 [{i}/{len(selected_stations)}] {station} 처리 중...")
            try:
                generated = generator.process_station(station)
                total_generated += generated
                print(f"INFO: {station} - {generated}개 페이지 생성")
            except Exception as e:
                print(f"ERROR: {station} 처리 중 오류 발생: {e}")
                continue
        
        # 완료 메시지
        elapsed_time = time.time() - start_time
        print("\n" + "=" * 50)
        print(f"INFO: 🎉 처리 완료!")
        print(f"INFO: 📊 통계:")
        print(f"INFO:   • 처리된 출발역: {len(selected_stations)}개")
        print(f"INFO:   • 생성된 페이지: {total_generated}개")
        print(f"INFO:   • 소요 시간: {elapsed_time:.1f}초")
        if total_generated > 0:
            print(f"INFO:   • 평균 속도: {total_generated/elapsed_time:.1f} 페이지/초")
        
        # 생성된 파일 목록 표시 (처음 10개만)
        if total_generated > 0:
            print(f"\nINFO: 💡 생성된 파일들:")
            pattern = os.path.join(config['output_folder'], "*열차시간표*")
            generated_files = glob.glob(pattern)
            for file_path in generated_files[:10]:
                file_size = os.path.getsize(file_path)
                print(f"INFO:   • {os.path.basename(file_path)} ({file_size:,} bytes)")
            if len(generated_files) > 10:
                print(f"INFO:   • ... 외 {len(generated_files) - 10}개 파일")
        else:
            print(f"\nWARNING: ⚠️ 생성된 페이지가 없습니다.")
            
        # GitHub Actions 출력 변수 설정
        if os.getenv('GITHUB_ACTIONS'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
                f.write(f"generated_count={total_generated}\n")
                f.write(f"processed_stations={len(selected_stations)}\n")
                f.write(f"execution_time={elapsed_time:.1f}\n")
            
    except KeyboardInterrupt:
        print("\nWARNING: ❌ 사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"\nERROR: ❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        # GitHub Actions에서 오류 발생 시 exit code 1
        if os.getenv('GITHUB_ACTIONS'):
            exit(1)

if __name__ == "__main__":
    main()
