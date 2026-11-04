import os
import sqlite3
import hashlib
import re
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from backend.settings import TEAM_PASSWORD
DB_PATH = "/workspace/data/app.db"
NEIGHBORHOOD = "불당동"
# 동 이름 → 대략적인 중심 좌표(위도, 경도). 정확한 건물 좌표가 아니라 동 단위 근사치입니다.
# (이 서버에서는 지오코딩 API를 쓸 수 없어, 공개적으로 알려진 천안시 동별 대략 위치를 사용했습니다.
#  실제 서비스에서는 건물 단위 정확한 좌표로 교체하는 걸 권장합니다.)
NEIGHBORHOOD_COORDS = {
    "불당동": (36.8183, 127.1142), "청당동": (36.8138, 127.1098), "청수동": (36.8231, 127.1065),
    "쌍용동": (36.8065, 127.1180), "성정동": (36.8135, 127.1223), "백석동": (36.8257, 127.1322),
    "두정동": (36.8389, 127.1310), "와촌동": (36.8043, 127.1108), "차암동": (36.8300, 127.1210),
    "업성동": (36.8420, 127.1430), "신당동": (36.8168, 127.1308), "부대동": (36.8470, 127.1480),
    "성성동": (36.8080, 127.0980), "성거읍": (36.8870, 127.1660), "입장면": (36.9390, 127.1780),
    "직산읍": (36.8690, 127.1860), "성환읍": (36.9290, 127.1480),
    "대흥동": (36.8102, 127.1479), "성황동": (36.8160, 127.1540), "문화동": (36.8140, 127.1510),
    "사직동": (36.8070, 127.1550), "영성동": (36.8120, 127.1570), "오룡동": (36.8030, 127.1600),
    "원성동": (36.8000, 127.1530), "유량동": (36.7950, 127.1460), "구성동": (36.8000, 127.1400),
    "청수동2": (36.8231, 127.1065), "삼룡동": (36.7900, 127.1500), "구룡동": (36.7870, 127.1570),
    "신방동": (36.7990, 127.1350), "용곡동": (36.7930, 127.1280), "봉명동": (36.8089, 127.1469),
    "다가동": (36.8050, 127.1430), "신부동": (36.8057, 127.1487), "안서동": (36.7870, 127.1350),
    "청당동2": (36.8138, 127.1098), "광덕면": (36.8650, 127.2250), "동면": (36.7900, 127.2250),
    "목천읍": (36.8070, 127.2280), "병천면": (36.8450, 127.2650), "북면": (36.8900, 127.0900),
    "성남면": (36.7450, 127.2350), "수신면": (36.7500, 127.2800), "풍세면": (36.7390, 127.2050),
}
DEFAULT_COORDS = (36.8151, 127.1139)  # 천안시청 인근 (동 정보가 없을 때의 기본값)
def coords_for_neighborhoods(neighborhoods: list[str]):
    for name in neighborhoods:
        if name in NEIGHBORHOOD_COORDS:
            return NEIGHBORHOOD_COORDS[name]
    return DEFAULT_COORDS
def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
def as_list(value: str):
    return [item.strip() for item in value.split(",") if item.strip()]
def normalize_nickname(nickname: str):
    return " ".join(nickname.strip().split()).casefold()
def add_column(conn, table, column, definition):
    fields = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in fields:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
def migrate_space_id_optional(conn):
    """학습 공간 선택을 선택사항으로 바꾸면서, 예전에 만들어진 DB는 space_id가 NOT NULL로 박혀 있을 수
    있어 요청을 보내도 못 들어갑니다. SQLite는 컬럼의 NOT NULL을 직접 못 바꾸므로, 같은 컬럼 구성으로
    테이블을 다시 만들어 데이터를 그대로 옮깁니다."""
    info = conn.execute("PRAGMA table_info(learning_requests)").fetchall()
    space_col = next((row for row in info if row[1] == "space_id"), None)
    if not space_col or not space_col[3]:
        return  # 테이블이 아직 없거나, 이미 nullable이면 손댈 것 없음
    columns = [row[1] for row in info]
    col_defs = []
    for row in info:
        name, type_, notnull, default = row[1], row[2] or "TEXT", row[3], row[4]
        if name == "id":
            col_defs.append("id INTEGER PRIMARY KEY AUTOINCREMENT")
            continue
        piece = f"{name} {type_}"
        if notnull and name != "space_id":
            piece += " NOT NULL"
        if default is not None:
            piece += f" DEFAULT {default}"
        col_defs.append(piece)
    conn.execute("ALTER TABLE learning_requests RENAME TO learning_requests_old")
    conn.execute(f"CREATE TABLE learning_requests ({', '.join(col_defs)})")
    cols_csv = ", ".join(columns)
    conn.execute(f"INSERT INTO learning_requests ({cols_csv}) SELECT {cols_csv} FROM learning_requests_old")
    conn.execute("DROP TABLE learning_requests_old")
def restore_default_candidates(conn):
    """Keep existing records and refresh only verified public-space records."""
    rows = [
        (
            "space", "천안시 성정평생학습관", "ChatGPT,캡컷,캔바", "입문,초급,중급",
            "스마트폰,노트북,태블릿", "충청남도 천안시 서북구 성정중4길 29",
            "", "https://www.cheonan.go.kr/women/",
            "천안시 성정평생학습관 공식 안내", "2026-11-03 11:46 KST",
            "천안시 성정평생학습관입니다.", "공식 안내에서 위치 확인", "성정동",
            0, "not_applicable", "평생학습관 · 충청남도 천안시 서북구 성정중4길 29",
            "공식 안내에서 확인", "공식 안내에서 강좌 일정과 수강 신청 방법 확인"
        ),
        (
            "space", "천안중앙도서관", "ChatGPT,캡컷,캔바", "입문,초급,중급",
            "스마트폰,노트북,태블릿", "충청남도 천안시 동남구 중앙로 118",
            "평일 오전,평일 오후,평일 저녁,주말 오전,주말 오후", "https://www.cheonan.go.kr/lib.do",
            "천안중앙도서관 공식 안내", "2026-11-03 11:46 KST",
            "천안시가 운영하는 공공도서관입니다.", "공식 안내에서 위치 확인", "대흥동",
            0, "not_applicable", "공공도서관 · 충청남도 천안시 동남구 중앙로 118",
            "일반열람실 매일 08:00~22:00 · 자료실 평일 09:00~22:00, 주말 09:00~18:00", "도서관 공식 안내에서 자료실별 이용 시간과 프로그램 확인"
        ),
    ]
    for row in rows:
        existing = conn.execute("SELECT id FROM candidates WHERE name=? AND kind='space' AND mentor_user_id IS NULL", (row[1],)).fetchone()
        values = (*row[2:15], row[15], row[16], row[17])
        if existing:
            conn.execute("""UPDATE candidates SET tools=?, levels=?, devices=?, regions=?, times=?, official_url=?, source=?, source_date=?, description=?, distance=?, neighborhood=?, consent_confirmed=?, verification_status=?, facility=?, operating_hours=?, usage_procedure=? WHERE id=?""", (*values, existing["id"]))
        else:
            conn.execute("""INSERT INTO candidates (kind,name,tools,levels,devices,regions,times,official_url,source,source_date,description,distance,neighborhood,consent_confirmed,verification_status,facility,operating_hours,usage_procedure) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", row)
def add_sample_candidates(conn):
    source = "임시 샘플 데이터 (실제 확인 필요)"
    source_date = "2026-11-03"
    mentors = [
        ("박지은", "wldms2026", "ChatGPT", "입문", "스마트폰", "평일 오전,평일 오후", "불당동,백석동", "서북구", "스마트폰으로 ChatGPT 처음 쓰는 분께 안내문·메시지 쓰는 법을 알려드려요."),
        ("이수현", "soohyun01", "캡컷", "초급", "스마트폰,태블릿", "평일 저녁,주말 오전", "쌍용동,성정동", "서북구", "짧은 영상 편집과 자막 넣는 법을 차근차근 알려드려요."),
        ("정하늘", "skyhaneul1", "캔바", "중급", "노트북,태블릿", "주말 오후", "두정동,신당동", "서북구", "행사 홍보물, 카드뉴스 디자인을 도와드려요."),
        ("최은비", "eunbi2026", "ChatGPT", "초급", "스마트폰,노트북", "평일 오후,주말 오전", "신부동,봉명동", "동남구", "자기소개서나 생활 글쓰기를 ChatGPT로 다듬는 법을 알려드려요."),
        ("한도윤", "doyoon0812", "캡컷", "입문", "스마트폰", "평일 저녁", "구성동,대흥동", "동남구", "사진·영상을 이어 붙여 짧은 영상 만드는 법을 알려드려요."),
        ("윤서아", "seoah2026a", "캔바", "입문", "노트북", "주말 오전,주말 오후", "성정동,와촌동", "서북구", "발표자료와 안내 포스터 만드는 법을 쉽게 알려드려요."),
    ]
    spaces = [
        ("쌍용2동 행정복지센터 정보화교실", "주민센터 정보화교실", "ChatGPT,캡컷,캔바", "입문,초급,중급", "스마트폰,노트북,태블릿", "평일 오전,평일 오후", "쌍용동", "서북구", "충청남도 천안시 서북구 쌍용동 (정확 주소 확인 필요)", "공식 안내에서 확인 필요", "주민센터 공식 안내 또는 방문 접수에서 이용 절차 확인"),
        ("성정동 행정복지센터 정보화교실", "주민센터 정보화교실", "ChatGPT,캔바", "입문,초급", "스마트폰,노트북", "평일 오후,주말 오전", "성정동", "서북구", "충청남도 천안시 서북구 성정동 (정확 주소 확인 필요)", "공식 안내에서 확인 필요", "주민센터 공식 안내 또는 방문 접수에서 이용 절차 확인"),
        ("두정동 작은도서관", "작은도서관", "ChatGPT,캡컷,캔바", "입문,초급,중급", "스마트폰,노트북,태블릿", "평일 오전,평일 오후,주말 오전", "두정동,백석동", "서북구", "충청남도 천안시 서북구 두정동 (정확 주소 확인 필요)", "공식 안내에서 확인 필요", "도서관 공식 안내에서 좌석·프로그램 이용 절차 확인"),
        ("천안시 성정평생학습관", "평생학습관", "ChatGPT,캡컷,캔바", "입문,초급,중급", "스마트폰,노트북,태블릿", "평일 오전,평일 오후,평일 저녁", "성정동,신당동", "서북구", "충청남도 천안시 서북구 성정동 (정확 주소 확인 필요)", "공식 안내에서 확인 필요", "평생학습관 공식 안내에서 강좌·좌석 이용 절차 확인"),
        ("신부동 작은도서관", "작은도서관", "ChatGPT,캔바", "입문,초급", "스마트폰,노트북", "평일 오후,주말 오후", "신부동,봉명동", "동남구", "충청남도 천안시 동남구 신부동 (정확 주소 확인 필요)", "공식 안내에서 확인 필요", "도서관 공식 안내에서 좌석 이용 절차 확인"),
    ]
    for nickname, password, tool, level, devices, times, neighborhoods, region, description in mentors:
        nickname_key = normalize_nickname(nickname)
        conn.execute("""INSERT OR IGNORE INTO users (nickname,nickname_key,password_hash,role,mentor_verification_status,mentor_consent_confirmed)
            VALUES (?,?,?,?,?,?)""", (nickname, nickname_key, hashlib.sha256(password.encode()).hexdigest(), "mentor", "pending", 1))
        user = conn.execute("SELECT id, role FROM users WHERE nickname_key=?", (nickname_key,)).fetchone()
        if user and user["role"] == "mentor":
            exists = conn.execute("SELECT id FROM candidates WHERE mentor_user_id=?", (user["id"],)).fetchone()
            if not exists:
                conn.execute("""INSERT INTO candidates (kind,name,tools,levels,devices,regions,times,official_url,source,source_date,description,distance,neighborhood,mentor_user_id,consent_confirmed,verification_status)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", ("mentor", nickname, tool, level, devices, region, times, "", source, source_date, description, "거리 정보는 확인 필요", neighborhoods, user["id"], 1, "pending"))
    for name, facility, tools, levels, devices, times, neighborhoods, region, address, hours, procedure in spaces:
        exists = conn.execute("SELECT id FROM candidates WHERE kind='space' AND name=? AND source=?", (name, source)).fetchone()
        if not exists:
            conn.execute("""INSERT INTO candidates (kind,name,tools,levels,devices,regions,times,official_url,source,source_date,description,distance,neighborhood,consent_confirmed,verification_status,facility,operating_hours,usage_procedure)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", ("space", name, tools, levels, devices, region, times, "", source, source_date, address, "거리 정보는 확인 필요", neighborhoods, 0, "pending", facility, hours, procedure))
def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, name TEXT NOT NULL,
            tools TEXT NOT NULL, levels TEXT NOT NULL, devices TEXT NOT NULL, regions TEXT NOT NULL,
            times TEXT NOT NULL, official_url TEXT NOT NULL, source TEXT NOT NULL,
            source_date TEXT NOT NULL, description TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS recommendation_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tool TEXT NOT NULL, course_name TEXT,
            level TEXT NOT NULL, device TEXT NOT NULL, region TEXT NOT NULL, time_slot TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nickname TEXT UNIQUE NOT NULL,
            nickname_key TEXT UNIQUE, password_hash TEXT NOT NULL, role TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS saved_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, candidate_id INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, candidate_id)
        );
        CREATE TABLE IF NOT EXISTS learning_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, mentor_id INTEGER NOT NULL,
            space_id INTEGER, status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, candidate_id INTEGER NOT NULL,
            request_id INTEGER, content TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        add_column(conn, "users", "nickname_key", "TEXT")
        add_column(conn, "users", "mentor_verification_status", "TEXT DEFAULT 'not_applicable'")
        add_column(conn, "users", "mentor_consent_confirmed", "INTEGER DEFAULT 0")
        add_column(conn, "candidates", "distance", "TEXT DEFAULT '거리 정보는 공식 안내에서 확인'")
        add_column(conn, "candidates", "neighborhood", "TEXT DEFAULT '불당동'")
        add_column(conn, "candidates", "mentor_user_id", "INTEGER")
        add_column(conn, "candidates", "consent_confirmed", "INTEGER DEFAULT 0")
        add_column(conn, "candidates", "verification_status", "TEXT DEFAULT 'pending'")
        add_column(conn, "candidates", "facility", "TEXT DEFAULT ''")
        add_column(conn, "candidates", "operating_hours", "TEXT DEFAULT ''")
        add_column(conn, "candidates", "usage_procedure", "TEXT DEFAULT ''")
        add_column(conn, "learning_requests", "learner_note", "TEXT DEFAULT ''")
        add_column(conn, "learning_requests", "mentor_note", "TEXT DEFAULT ''")
        add_column(conn, "learning_requests", "learner_note_updated_at", "TEXT")
        add_column(conn, "learning_requests", "mentor_note_updated_at", "TEXT")
        # 멘토가 수락 대기 요청에서 학습자가 뭘 배우고 싶은지(도구/수준/키워드)와
        # 어떤 조건(기기/시간/동)으로 찾았는지 볼 수 있도록, 요청 생성 시점의 조건을 함께 저장합니다.
        add_column(conn, "learning_requests", "tool", "TEXT DEFAULT ''")
        add_column(conn, "learning_requests", "level", "TEXT DEFAULT ''")
        add_column(conn, "learning_requests", "devices", "TEXT DEFAULT ''")
        add_column(conn, "learning_requests", "time_slots", "TEXT DEFAULT ''")
        add_column(conn, "learning_requests", "neighborhoods", "TEXT DEFAULT ''")
        add_column(conn, "learning_requests", "keyword", "TEXT DEFAULT ''")
        # 멘토가 도구뿐 아니라 그 안에서 가르칠 수 있는 구체적인 주제를 등록할 수 있도록 합니다.
        add_column(conn, "candidates", "topics", "TEXT DEFAULT ''")
        add_column(conn, "reviews", "request_id", "INTEGER")
        migrate_space_id_optional(conn)
        conn.execute("UPDATE users SET mentor_verification_status='pending' WHERE role='mentor' AND (mentor_verification_status IS NULL OR mentor_verification_status='not_applicable')")
        conn.execute("UPDATE users SET mentor_verification_status='not_applicable' WHERE role='learner' AND mentor_verification_status IS NULL")
        user_rows = conn.execute("SELECT id, nickname FROM users WHERE nickname_key IS NULL OR nickname_key = ''").fetchall()
        for user_row in user_rows:
            conn.execute("UPDATE users SET nickname_key=? WHERE id=?", (normalize_nickname(user_row["nickname"]), user_row["id"]))
        try:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_nickname_key_unique ON users(nickname_key)")
        except sqlite3.IntegrityError:
            pass
        conn.execute("DELETE FROM candidates WHERE source='임시 샘플 데이터 (실제 확인 필요)'")
        restore_default_candidates(conn)
app = FastAPI()
init_db()
class AuthInput(BaseModel):
    nickname: str
    password: str
    role: str
class LoginInput(BaseModel):
    nickname: str
    password: str
    role: str
class RecommendationRequest(BaseModel):
    tool: str
    course_name: str | None = None
    level: str
    devices: list[str]
    time_slots: list[str]
    neighborhoods: list[str]
    keyword: str = ""
class MentorProfile(BaseModel):
    user_id: int
    tools: list[str]
    devices: list[str]
    times: list[str]
    neighborhoods: list[str]
    topics: list[str] = []
    consent_confirmed: bool
class SaveInput(BaseModel):
    user_id: int
    candidate_id: int
class LearningRequestInput(BaseModel):
    user_id: int
    mentor_id: int
    space_id: int | None = None
    tool: str = ""
    level: str = ""
    devices: list[str] = []
    time_slots: list[str] = []
    neighborhoods: list[str] = []
    keyword: str = ""
class MentorRequestAction(BaseModel):
    user_id: int
class AppointmentNoteInput(BaseModel):
    user_id: int
    note: str
class ReviewInput(BaseModel):
    user_id: int
    request_id: int
    content: str
class TeamAccessInput(BaseModel):
    password: str
class TeamStatusInput(BaseModel):
    status: str
def require_team_password(team_password: str | None):
    if not TEAM_PASSWORD or team_password is None or team_password.strip() != TEAM_PASSWORD:
        raise HTTPException(401, "팀 비밀번호가 맞지 않습니다.")
def public_user(row):
    return {"id": row["id"], "nickname": row["nickname"], "role": row["role"]}
ANY_TOOL = "상관없어요"  # 학습자가 특정 도구 없이 "멘토 추천대로/아무거나 괜찮음"을 선택했을 때의 값
LEVEL_ORDER = ["입문", "초급", "중급"]
MAX_SCORE = 15
SPACE_MAX_SCORE = 8  # 공간은 도구(4)+수준(3)을 빼고 기기(2)+시간(2)+동(2)+키워드(2)만 반영
def overlap_tier(requested: list[str], available: list[str]):
    """match: at least one requested option is covered · miss: no overlap at all."""
    if not requested: return "miss", []
    matched = [value for value in requested if value in available]
    return ("match", matched) if matched else ("miss", [])
def level_tier(requested: str, available: list[str]):
    if not requested or requested not in LEVEL_ORDER or not available: return "miss", None
    req_index = LEVEL_ORDER.index(requested)
    distances = [abs(req_index - LEVEL_ORDER.index(level)) for level in available if level in LEVEL_ORDER]
    if not distances: return "miss", None
    closest = min(distances)
    tier = "match" if closest == 0 else "partial" if closest == 1 else "miss"
    return tier, closest
def candidate_item(row, request=None):
    item = dict(row)
    for key in ("tools", "levels", "devices", "regions", "times"):
        item[key] = as_list(item[key])
    item["neighborhoods"] = as_list(item.get("neighborhood", ""))
    item["topics"] = as_list(item.get("topics", "") or "")
    item["lat"], item["lng"] = coords_for_neighborhoods(item["neighborhoods"])
    item["consent_confirmed"] = bool(item.get("consent_confirmed", 0))
    if item["kind"] == "mentor" and item.get("verification_status") != "verified":
        item["verification_status"] = "pending"
    score, matches = 0, []
    match_detail = {}
    is_space = item["kind"] == "space"
    if request:
        # 공간(도서관·학습관 등)은 특정 도구·수준을 "가르치지" 않고 누구나 쓸 수 있는 장소이므로,
        # 도구·수준은 멘토에게만 의미 있는 매칭 기준입니다. 공간은 기기/시간/동만 비교합니다.
        if not is_space:
            if request.tool == ANY_TOOL:
                # 도구를 특정하지 않은 학습자는 모든 멘토와 도구 기준으로는 항상 "일치"로 취급합니다.
                tool_tier = "match"
                score += 4; matches.append("도구는 상관없음 · 멘토 추천대로 가능")
                match_detail["tool"] = {"tier": "match", "label": ANY_TOOL}
            else:
                tool_tier = "match" if request.tool in item["tools"] else "miss"
                if tool_tier == "match": score += 4; matches.append(f"{request.tool} 학습 가능")
                match_detail["tool"] = {"tier": tool_tier, "label": request.tool if tool_tier == "match" else (", ".join(item["tools"]) or "정보 없음")}

            lvl_tier, lvl_distance = level_tier(request.level, item["levels"])
            if lvl_tier == "match": score += 3; matches.append(f"{request.level} 수준에 맞음")
            elif lvl_tier == "partial": score += 1; matches.append(f"수준이 한 단계 차이 · {', '.join(item['levels'])}")
            match_detail["level"] = {"tier": lvl_tier, "label": ", ".join(item["levels"]) or "정보 없음"}

        device_tier, matched_devices = overlap_tier(request.devices, item["devices"])
        if device_tier == "match": score += 2; matches.append(f"사용 기기와 맞음 · {', '.join(matched_devices)}")
        match_detail["device"] = {"tier": device_tier, "label": ", ".join(matched_devices) if matched_devices else (", ".join(item["devices"]) or "정보 없음")}

        time_tier, matched_times = overlap_tier(request.time_slots, item["times"])
        if time_tier == "match": score += 2; matches.append(f"가능한 시간대와 맞음 · {', '.join(matched_times)}")
        match_detail["time"] = {"tier": time_tier, "label": ", ".join(matched_times) if matched_times else (", ".join(item["times"]) or "정보 없음")}

        neighborhood_tier, matched_neighborhoods = overlap_tier(request.neighborhoods, item["neighborhoods"])
        if neighborhood_tier == "match": score += 2; matches.append(f"선택한 동과 맞음 · {', '.join(matched_neighborhoods)}")
        match_detail["neighborhood"] = {"tier": neighborhood_tier, "label": ", ".join(matched_neighborhoods) if matched_neighborhoods else (", ".join(item["neighborhoods"]) or "정보 없음")}

        if request.keyword:
            keyword_tier = "match" if request.keyword.lower() in (item["name"] + item["description"] + ",".join(item["tools"]) + ",".join(item["topics"])).lower() else "miss"
            if keyword_tier == "match": score += 2; matches.append("입력한 학습 내용과 관련됨")
            match_detail["keyword"] = {"tier": keyword_tier, "label": request.keyword}
    item["score"] = score
    max_score = SPACE_MAX_SCORE if is_space else MAX_SCORE
    item["match_percent"] = round(score / max_score * 100) if request else None
    item["match_detail"] = match_detail
    area_label = item["neighborhoods"][0] if item["neighborhoods"] else NEIGHBORHOOD
    item["reason"] = " · ".join(matches) or f"{area_label} 인근에서 공식 안내를 확인할 수 있는 후보입니다"
    return item
@app.get("/api/health")
def health():
    return {"ok": True}
@app.post("/api/auth/signup")
def signup(data: AuthInput):
    nickname = " ".join(data.nickname.strip().split())
    nickname_key = normalize_nickname(nickname)
    if len(nickname) < 2 or len(data.password) < 8 or data.role not in ("learner", "mentor"):
        raise HTTPException(400, "닉네임·비밀번호·역할을 다시 확인해 주세요. 비밀번호는 8자리 이상이어야 합니다.")
    with get_db() as conn:
        try:
            cursor = conn.execute("INSERT INTO users (nickname,nickname_key,password_hash,role,mentor_verification_status,mentor_consent_confirmed) VALUES (?,?,?,?,?,?)", (nickname, nickname_key, hashlib.sha256(data.password.encode()).hexdigest(), data.role, 'pending' if data.role == 'mentor' else 'not_applicable', 0))
            row = conn.execute("SELECT * FROM users WHERE id=?", (cursor.lastrowid,)).fetchone()
        except sqlite3.IntegrityError:
            raise HTTPException(409, "이미 사용 중인 닉네임입니다.")
    return public_user(row)
@app.post("/api/auth/login")
def login(data: LoginInput):
    nickname_key = normalize_nickname(data.nickname)
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE nickname_key=? AND password_hash=? AND role=?", (nickname_key, hashlib.sha256(data.password.encode()).hexdigest(), data.role)).fetchone()
    if not row:
        raise HTTPException(401, "닉네임·비밀번호·역할을 확인해 주세요.")
    return public_user(row)
@app.post("/api/recommendations")
def recommendations(request: RecommendationRequest):
    with get_db() as conn:
        cursor = conn.execute("INSERT INTO recommendation_requests (tool,course_name,level,device,region,time_slot) VALUES (?,?,?,?,?,?)", (request.tool, request.course_name, request.level, ",".join(request.devices), ",".join(request.neighborhoods), ",".join(request.time_slots)))
        rows = conn.execute("SELECT * FROM candidates").fetchall()
    mentor_rows = [row for row in rows if row["kind"] == "mentor" and row["verification_status"] == "verified"]
    space_rows = [row for row in rows if row["kind"] == "space"]
    result = {"mentor": [], "space": []}
    for row in mentor_rows + space_rows:
        item = candidate_item(row, request)
        # 공간은 도구(4점)가 빠져서 기준점을 낮춰야 기기/시간/동 중 하나만 맞아도 후보로 집계됩니다.
        threshold = 2 if item["kind"] == "space" else 4
        if item["score"] >= threshold:
            result[item["kind"]].append(item)
    for key in result:
        result[key] = sorted(result[key], key=lambda x: x["score"], reverse=True)
    if len(result["mentor"]) < 2:
        seen = {item["id"] for item in result["mentor"]}
        result["mentor"].extend(candidate_item(row, request) for row in mentor_rows if row["id"] not in seen)
    if len(result["space"]) < 3:
        seen = {item["id"] for item in result["space"]}
        result["space"].extend(candidate_item(row, request) for row in space_rows if row["id"] not in seen)
    result["mentor"] = result["mentor"][:2]
    result["space"] = result["space"][:3]
    return {"request_id": cursor.lastrowid, "request": {**request.model_dump(), "neighborhood": ", ".join(request.neighborhoods) or NEIGHBORHOOD}, "results": result}
@app.post("/api/learning-requests")
def create_learning_request(data: LearningRequestInput):
    with get_db() as conn:
        user = conn.execute("SELECT id FROM users WHERE id=? AND role='learner'", (data.user_id,)).fetchone()
        mentor = conn.execute("SELECT id FROM candidates WHERE id=? AND kind='mentor' AND verification_status='verified'", (data.mentor_id,)).fetchone()
        # 학습 공간은 추천일 뿐이라 선택사항입니다 — 고른 경우에만 유효한 공간인지 확인합니다.
        space = None
        if data.space_id is not None:
            space = conn.execute("SELECT id FROM candidates WHERE id=? AND kind='space'", (data.space_id,)).fetchone()
            if not space:
                raise HTTPException(400, "선택한 학습 공간을 다시 확인해 주세요.")
        if not user or not mentor:
            raise HTTPException(400, "선택한 멘토를 다시 확인해 주세요.")
        pending = conn.execute("SELECT id FROM learning_requests WHERE user_id=? AND status='pending' LIMIT 1", (data.user_id,)).fetchone()
        if pending:
            raise HTTPException(400, "대기중인 멘토 요청이 있어 수락·거절·취소 전에는 새 멘토 요청을 보낼 수 없습니다.")
        cursor = conn.execute("""INSERT INTO learning_requests (user_id,mentor_id,space_id,tool,level,devices,time_slots,neighborhoods,keyword)
            VALUES (?,?,?,?,?,?,?,?,?)""", (data.user_id, data.mentor_id, data.space_id, data.tool, data.level, ",".join(data.devices), ",".join(data.time_slots), ",".join(data.neighborhoods), data.keyword))
    return {"id": cursor.lastrowid, "status": "pending"}
@app.post("/api/learning-requests/{request_id}/complete")
def complete_learning_request(request_id: int, data: LearningRequestInput):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM learning_requests WHERE id=? AND user_id=?", (request_id, data.user_id)).fetchone()
        if not row:
            raise HTTPException(404, "요청 기록을 찾지 못했습니다.")
        conn.execute("UPDATE learning_requests SET status='completed', completed_at=CURRENT_TIMESTAMP WHERE id=?", (request_id,))
    return {"ok": True, "status": "completed"}
@app.post("/api/saved")
def save_candidate(data: SaveInput):
    with get_db() as conn:
        conn.execute("INSERT OR IGNORE INTO saved_candidates (user_id,candidate_id) VALUES (?,?)", (data.user_id, data.candidate_id))
    return {"ok": True}
@app.post("/api/reviews")
def add_review(data: ReviewInput):
    if not data.content.strip():
        raise HTTPException(400, "후기 내용을 입력해 주세요.")
    with get_db() as conn:
        request = conn.execute("SELECT * FROM learning_requests WHERE id=? AND user_id=? AND status='completed'", (data.request_id, data.user_id)).fetchone()
        if not request:
            raise HTTPException(400, "학습을 마친 뒤에만 이용 후기를 남길 수 있습니다.")
        conn.execute("INSERT INTO reviews (user_id,candidate_id,request_id,content) VALUES (?,?,?,?)", (data.user_id, request["mentor_id"], data.request_id, data.content.strip()))
    return {"ok": True}
@app.get("/api/history/{user_id}")
def history(user_id: int):
    with get_db() as conn:
        saved = conn.execute("SELECT c.* FROM saved_candidates s JOIN candidates c ON c.id=s.candidate_id WHERE s.user_id=? ORDER BY s.id DESC", (user_id,)).fetchall()
        requests = conn.execute("""SELECT lr.*, m.name AS mentor_name, s.name AS space_name, m.official_url AS mentor_url
            FROM learning_requests lr JOIN candidates m ON m.id=lr.mentor_id LEFT JOIN candidates s ON s.id=lr.space_id
            WHERE lr.user_id=? ORDER BY lr.id DESC""", (user_id,)).fetchall()
        reviews = conn.execute("SELECT r.*, c.name FROM reviews r JOIN candidates c ON c.id=r.candidate_id WHERE r.user_id=? ORDER BY r.id DESC", (user_id,)).fetchall()
    return {"saved": [candidate_item(row) for row in saved], "requests": [dict(row) for row in requests], "reviews": [dict(row) for row in reviews]}
@app.get("/api/mentor/{user_id}")
def mentor_profile(user_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM candidates WHERE mentor_user_id=? LIMIT 1", (user_id,)).fetchone()
    return candidate_item(row) if row else None
@app.put("/api/mentor")
def update_mentor(data: MentorProfile):
    if not data.tools or not data.devices or not data.times or not data.neighborhoods:
        raise HTTPException(400, "가능 도구·기기·시간·동을 모두 선택해 주세요.")
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=? AND role='mentor'", (data.user_id,)).fetchone()
        if not user:
            raise HTTPException(403, "멘토 계정만 수정할 수 있습니다.")
        row = conn.execute("SELECT id FROM candidates WHERE mentor_user_id=?", (data.user_id,)).fetchone()
        if row:
            conn.execute("UPDATE candidates SET tools=?, devices=?, times=?, neighborhood=?, topics=?, consent_confirmed=?, verification_status='pending', source_date=? WHERE id=?", (",".join(data.tools), ",".join(data.devices), ",".join(data.times), ",".join(data.neighborhoods), ",".join(data.topics), int(data.consent_confirmed), "2026-11-03", row["id"]))
        else:
            conn.execute("""INSERT INTO candidates (kind,name,tools,levels,devices,regions,times,official_url,source,source_date,description,distance,neighborhood,topics,mentor_user_id,consent_confirmed,verification_status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", ("mentor", user["nickname"], ",".join(data.tools), "입문,초급,중급", ",".join(data.devices), "천안시", ",".join(data.times), "", "멘토가 직접 입력한 안내", "2026-11-03", "수강 전 공식 안내 페이지에서 운영 정보를 확인해 주세요.", "거리 정보는 공식 안내에서 확인", ",".join(data.neighborhoods), ",".join(data.topics), data.user_id, int(data.consent_confirmed), "pending"))
        conn.execute("UPDATE users SET mentor_verification_status='pending', mentor_consent_confirmed=? WHERE id=?", (int(data.consent_confirmed), data.user_id))
    return {"ok": True, "verification_status": "pending"}
@app.post("/api/team/access")
def team_access(data: TeamAccessInput):
    if data.password.strip() != TEAM_PASSWORD:
        raise HTTPException(401, "팀 비밀번호가 맞지 않습니다.")
    return {"ok": True}
@app.get("/api/team/mentors")
def team_mentors(x_team_password: str | None = Header(default=None)):
    require_team_password(x_team_password)
    with get_db() as conn:
        rows = conn.execute("""SELECT u.id, u.nickname, u.mentor_verification_status, u.mentor_consent_confirmed,
            (SELECT c.tools FROM candidates c WHERE c.mentor_user_id=u.id ORDER BY c.id DESC LIMIT 1) AS tools,
            (SELECT c.times FROM candidates c WHERE c.mentor_user_id=u.id ORDER BY c.id DESC LIMIT 1) AS times
            FROM users u WHERE u.role='mentor' ORDER BY u.created_at DESC""").fetchall()
    return [{**dict(row), "tools": as_list(row["tools"] or ""), "times": as_list(row["times"] or ""), "consent_confirmed": bool(row["mentor_consent_confirmed"] or 0)} for row in rows]
@app.put("/api/team/mentors/{user_id}/status")
def update_mentor_status(user_id: int, data: TeamStatusInput, x_team_password: str | None = Header(default=None)):
    require_team_password(x_team_password)
    if data.status not in ("before_consent", "consented", "verified"):
        raise HTTPException(400, "변경할 상태를 다시 확인해 주세요.")
    with get_db() as conn:
        mentor = conn.execute("SELECT * FROM users WHERE id=? AND role='mentor'", (user_id,)).fetchone()
        candidate = conn.execute("SELECT * FROM candidates WHERE mentor_user_id=?", (user_id,)).fetchone()
        if not mentor:
            raise HTTPException(404, "멘토 계정을 찾지 못했습니다.")
        if data.status == "verified" and not candidate:
            raise HTTPException(400, "프로필을 입력한 멘토만 확인됨으로 변경할 수 있습니다.")
        consent = 0 if data.status == "before_consent" else 1
        verification = "verified" if data.status == "verified" else "pending"
        conn.execute("UPDATE users SET mentor_consent_confirmed=?, mentor_verification_status=? WHERE id=?", (consent, verification, user_id))
        if candidate:
            conn.execute("UPDATE candidates SET consent_confirmed=?, verification_status=? WHERE mentor_user_id=?", (consent, verification, user_id))
    return {"ok": True, "status": data.status}
@app.get("/api/mentor-requests/{user_id}")
def mentor_requests(user_id: int):
    with get_db() as conn:
        mentor = conn.execute("SELECT id FROM candidates WHERE mentor_user_id=? AND kind='mentor'", (user_id,)).fetchone()
        if not mentor:
            return []
        rows = conn.execute("""SELECT lr.*, u.nickname AS learner_name, s.name AS space_name
            FROM learning_requests lr JOIN users u ON u.id=lr.user_id LEFT JOIN candidates s ON s.id=lr.space_id
            WHERE lr.mentor_id=? ORDER BY lr.id DESC""", (mentor["id"],)).fetchall()
    return [{**dict(row), "devices": as_list(row["devices"] or ""), "time_slots": as_list(row["time_slots"] or ""), "neighborhoods": as_list(row["neighborhoods"] or "")} for row in rows]
@app.post("/api/learning-requests/{request_id}/cancel")
def cancel_learning_request(request_id: int, data: MentorRequestAction):
    with get_db() as conn:
        request = conn.execute("SELECT * FROM learning_requests WHERE id=? AND user_id=?", (request_id, data.user_id)).fetchone()
        if not request:
            raise HTTPException(403, "이 요청을 취소할 권한이 없습니다.")
        if request["status"] != "pending":
            raise HTTPException(400, "대기중인 요청만 취소할 수 있습니다.")
        conn.execute("UPDATE learning_requests SET status='cancelled' WHERE id=?", (request_id,))
    return {"ok": True, "status": "cancelled"}
@app.post("/api/learning-requests/{request_id}/reject")
def reject_learning_request(request_id: int, data: MentorRequestAction):
    with get_db() as conn:
        mentor = conn.execute("SELECT id FROM candidates WHERE mentor_user_id=? AND kind='mentor'", (data.user_id,)).fetchone()
        request = conn.execute("SELECT * FROM learning_requests WHERE id=?", (request_id,)).fetchone()
        if not mentor or not request or request["mentor_id"] != mentor["id"]:
            raise HTTPException(403, "이 요청을 거절할 권한이 없습니다.")
        if request["status"] != "pending":
            raise HTTPException(400, "대기중인 요청만 거절할 수 있습니다.")
        conn.execute("UPDATE learning_requests SET status='cancelled' WHERE id=?", (request_id,))
    return {"ok": True, "status": "cancelled"}
@app.post("/api/learning-requests/{request_id}/confirm")
def confirm_learning_request(request_id: int, data: MentorRequestAction):
    with get_db() as conn:
        mentor = conn.execute("SELECT id FROM candidates WHERE mentor_user_id=? AND kind='mentor'", (data.user_id,)).fetchone()
        request = conn.execute("SELECT * FROM learning_requests WHERE id=?", (request_id,)).fetchone()
        if not mentor or not request or request["mentor_id"] != mentor["id"]:
            raise HTTPException(403, "이 요청을 수락할 권한이 없습니다.")
        if request["status"] != "pending":
            raise HTTPException(400, "대기중인 요청만 수락할 수 있습니다.")
        conn.execute("UPDATE learning_requests SET status='confirmed' WHERE id=?", (request_id,))
    return {"ok": True, "status": "confirmed"}
@app.put("/api/learning-requests/{request_id}/appointment-note")
def update_appointment_note(request_id: int, data: AppointmentNoteInput):
    note = data.note.strip()
    if len(note) > 200:
        raise HTTPException(400, "약속 쪽지는 200자 이내로 적어 주세요.")
    with get_db() as conn:
        request = conn.execute("SELECT * FROM learning_requests WHERE id=?", (request_id,)).fetchone()
        if not request or request["status"] != "confirmed":
            raise HTTPException(400, "확인됨 상태의 요청에서만 약속 메모를 작성할 수 있습니다.")
        has_phone = bool(re.search(r"(?:0\d{1,2}[\s-]?)?\d{3,4}[\s-]?\d{4}", note))
        has_email = bool(re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", note))
        if has_phone or has_email:
            raise HTTPException(400, "약속 메모에는 전화번호나 이메일 등 연락처를 적을 수 없습니다.")
        if request["user_id"] == data.user_id:
            note_column, time_column = "learner_note", "learner_note_updated_at"
        else:
            mentor = conn.execute("SELECT id FROM candidates WHERE mentor_user_id=? AND id=?", (data.user_id, request["mentor_id"])).fetchone()
            if not mentor:
                raise HTTPException(403, "이 약속 메모를 수정할 권한이 없습니다.")
            note_column, time_column = "mentor_note", "mentor_note_updated_at"
        conn.execute(f"UPDATE learning_requests SET {note_column}=?, {time_column}=CURRENT_TIMESTAMP WHERE id=?", (note, request_id))
        saved = conn.execute("SELECT learner_note, mentor_note, learner_note_updated_at, mentor_note_updated_at FROM learning_requests WHERE id=?", (request_id,)).fetchone()
    return {"ok": True, **dict(saved)}
@app.get("/api/mentor-reviews/{user_id}")
def mentor_reviews(user_id: int):
    with get_db() as conn:
        mentor = conn.execute("SELECT id FROM candidates WHERE mentor_user_id=? AND kind='mentor'", (user_id,)).fetchone()
        if not mentor:
            return []
        rows = conn.execute("""SELECT r.id, r.content, r.created_at, u.nickname AS learner_name
            FROM reviews r JOIN users u ON u.id=r.user_id
            WHERE r.candidate_id=? ORDER BY r.id DESC""", (mentor["id"],)).fetchall()
    return [dict(row) for row in rows]
