import os
import sqlite3
import hashlib
import re
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from backend.settings import TEAM_PASSWORD
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "app.db"))
NEIGHBORHOOD = "불당동"
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
            space_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
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
        conn.execute("UPDATE users SET mentor_verification_status='pending' WHERE role='mentor' AND (mentor_verification_status IS NULL OR mentor_verification_status='not_applicable')")
        conn.execute("UPDATE users SET mentor_verification_status='not_applicable' WHERE role='learner' AND mentor_verification_status IS NULL")
        user_rows = conn.execute("SELECT id, nickname FROM users WHERE nickname_key IS NULL OR nickname_key = ''").fetchall()
        for user_row in user_rows:
            conn.execute("UPDATE users SET nickname_key=? WHERE id=?", (normalize_nickname(user_row["nickname"]), user_row["id"]))
        try:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_nickname_key_unique ON users(nickname_key)")
        except sqlite3.IntegrityError:
            pass
        add_column(conn, "candidates", "distance", "TEXT DEFAULT '도보 10분'")
        add_column(conn, "candidates", "neighborhood", "TEXT DEFAULT '불당동'")
        add_column(conn, "candidates", "mentor_user_id", "INTEGER")       
        add_column(conn, "candidates", "consent_confirmed", "INTEGER DEFAULT 0")
        add_column(conn, "candidates", "verification_status", "TEXT DEFAULT 'pending'")
        add_column(conn, "candidates", "facility", "TEXT DEFAULT ''")
        add_column(conn, "candidates", "operating_hours", "TEXT DEFAULT ''")
        add_column(conn, "candidates", "usage_procedure", "TEXT DEFAULT ''")
        conn.execute("UPDATE users SET mentor_consent_confirmed=1 WHERE role='mentor' AND id IN (SELECT mentor_user_id FROM candidates WHERE consent_confirmed=1 AND mentor_user_id IS NOT NULL)")
        # 기존 appointment_note는 이전 버전 호환을 위해 남아 있을 수 있으나 더 이상 생성하거나 사용하지 않습니다.
        add_column(conn, "learning_requests", "learner_note", "TEXT DEFAULT ''")
        add_column(conn, "learning_requests", "mentor_note", "TEXT DEFAULT ''")
        add_column(conn, "learning_requests", "learner_note_updated_at", "TEXT")
        add_column(conn, "learning_requests", "mentor_note_updated_at", "TEXT")
        add_column(conn, "reviews", "request_id", "INTEGER")
        count = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        if count == 0:
            rows = [
                ("mentor", "불당 디지털 길잡이", "ChatGPT,캔바", "입문,초급", "스마트폰,노트북", "천안시 서북구", "평일 오전,평일 오후", "https://www.cheonan.go.kr/", "천안시 평생학습 안내 표본", "2026-10-15", "생활 속 문서 작성과 간단한 홍보물 만들기를 차근차근 돕습니다.", "도보 8분", NEIGHBORHOOD, 1, "verified"),
                ("mentor", "천안 AI 생활 멘토", "ChatGPT,캡컷", "입문,초급,중급", "스마트폰,노트북", "천안시 서북구", "평일 오후,주말 오전", "https://www.cheonan.go.kr/", "천안시 평생학습 안내 표본", "2026-10-15", "스마트폰으로 시작하는 AI 활용과 짧은 영상 편집을 안내합니다.", "도보 14분", NEIGHBORHOOD, 1, "verified"),
                ("mentor", "성성 창작 도우미", "캔바,캡컷", "초급,중급", "노트북,태블릿", "천안시 서북구", "주말 오후,평일 저녁", "https://www.cheonan.go.kr/", "천안시 문화·학습 안내 표본", "2026-10-15", "디자인과 영상 만들기를 실제 예제로 연습할 수 있습니다.", "도보 22분", NEIGHBORHOOD, 1, "verified"),
                ("space", "불당동 정보교육실", "ChatGPT,캔바", "입문,초급", "노트북,태블릿", "천안시 서북구", "평일 오전,평일 오후", "https://www.cheonan.go.kr/", "천안시 공공 학습공간 안내 표본", "2026-10-15", "노트북 기반 수업을 운영할 수 있는 공공 교육 공간입니다.", "도보 6분", NEIGHBORHOOD, 0, "not_applicable"),
                ("space", "천안시 평생학습관", "ChatGPT,캡컷,캔바", "입문,초급,중급", "스마트폰,노트북,태블릿", "천안시 서북구", "평일 오후,주말 오전,주말 오후", "https://www.cheonan.go.kr/", "천안시 평생학습관 안내 표본", "2026-10-15", "다양한 디지털 학습 프로그램을 확인할 수 있는 공공 학습 공간입니다.", "도보 17분", NEIGHBORHOOD, 0, "not_applicable"),
                ("space", "청년문화센터 학습존", "캡컷,캔바", "초급,중급", "노트북,태블릿", "천안시 동남구", "평일 저녁,주말 오후", "https://www.cheonan.go.kr/", "천안시 청년 문화 안내 표본", "2026-10-15", "콘텐츠 제작 연습에 어울리는 열린 학습 공간입니다.", "도보 25분", NEIGHBORHOOD, 0, "not_applicable"),
            ]
            conn.executemany("""INSERT INTO candidates (kind,name,tools,levels,devices,regions,times,official_url,source,source_date,description,distance,neighborhood,consent_confirmed,verification_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
        else:
            conn.execute("UPDATE candidates SET neighborhood = ? WHERE neighborhood IS NULL OR neighborhood = ''", (NEIGHBORHOOD,))
            conn.execute("UPDATE candidates SET verification_status = 'verified', consent_confirmed = 1 WHERE kind = 'mentor' AND mentor_user_id IS NULL AND (verification_status IS NULL OR verification_status = 'pending')")
            conn.execute("UPDATE candidates SET verification_status = 'not_applicable' WHERE kind = 'space' AND (verification_status IS NULL OR verification_status = 'pending')")
            space_details = [("노트북과 빔프로젝터를 갖춘 정보교육 시설", "평일 09:00~18:00", "공식 안내에서 교육 일정 확인 후 이용 신청", "불당동 정보교육실"), ("강의실과 디지털 학습 장비를 갖춘 평생학습 시설", "평일 09:00~21:00 · 주말 프로그램별 상이", "공식 안내에서 프로그램별 모집 일정 확인", "천안시 평생학습관"), ("콘텐츠 제작을 위한 열린 학습 공간", "평일 10:00~20:00 · 주말 10:00~17:00", "공식 안내에서 공간 운영 및 이용 방법 확인", "청년문화센터 학습존")]
            conn.executemany("UPDATE candidates SET facility=?, operating_hours=?, usage_procedure=? WHERE name=? AND kind='space'", space_details)
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
    device: str
    time_slot: str
    keyword: str = ""
class MentorProfile(BaseModel):
    user_id: int
    tools: list[str]
    times: list[str]
    consent_confirmed: bool
class SaveInput(BaseModel):
    user_id: int
    candidate_id: int
class LearningRequestInput(BaseModel):
    user_id: int
    mentor_id: int
    space_id: int
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
def candidate_item(row, request=None):
    item = dict(row)
    for key in ("tools", "levels", "devices", "regions", "times"):
        item[key] = as_list(item[key])
    item["consent_confirmed"] = bool(item.get("consent_confirmed", 0))
    if item["kind"] == "mentor" and item.get("verification_status") != "verified":
        item["verification_status"] = "pending"
    score, matches = 0, []
    if request:
        if request.tool in item["tools"]: score += 4; matches.append(f"{request.tool} 학습 가능")
        if request.level in item["levels"]: score += 3; matches.append(f"{request.level} 수준에 맞음")
        if request.device in item["devices"]: score += 2; matches.append(f"{request.device} 사용 가능")
        if request.time_slot in item["times"]: score += 2; matches.append("가능한 시간대와 맞음")
        if request.keyword and request.keyword.lower() in (item["name"] + item["description"] + ",".join(item["tools"])).lower(): score += 2; matches.append("입력한 학습 내용과 관련됨")
    item["score"] = score
    item["reason"] = " · ".join(matches) or f"{NEIGHBORHOOD} 인근에서 확인할 수 있는 후보입니다"
    return item
@app.get("/api/health")
def health(): return {"ok": True}
@app.post("/api/auth/signup")
def signup(data: AuthInput):
    nickname = " ".join(data.nickname.strip().split())
    nickname_key = normalize_nickname(nickname)
    if len(nickname) < 2 or len(data.password) < 4 or data.role not in ("learner", "mentor"):
        raise HTTPException(400, "닉네임·비밀번호·역할을 다시 확인해 주세요.")
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
    if not row: raise HTTPException(401, "닉네임·비밀번호·역할을 확인해 주세요.")
    return public_user(row)
@app.post("/api/recommendations")
def recommendations(request: RecommendationRequest):
    with get_db() as conn:
        cursor = conn.execute("INSERT INTO recommendation_requests (tool,course_name,level,device,region,time_slot) VALUES (?,?,?,?,?,?)", (request.tool, request.course_name, request.level, request.device, NEIGHBORHOOD, request.time_slot))
        rows = conn.execute("SELECT * FROM candidates").fetchall()
    mentor_rows = [row for row in rows if row["kind"] == "mentor" and row["verification_status"] == "verified"]
    space_rows = [row for row in rows if row["kind"] == "space"]
    result = {"mentor": [], "space": []}
    for row in mentor_rows + space_rows:
        item = candidate_item(row, request)
        if item["score"] >= 4: result[item["kind"]].append(item)
    for key in result: result[key] = sorted(result[key], key=lambda x: x["score"], reverse=True)
    if len(result["mentor"]) < 2:
        seen = {item["id"] for item in result["mentor"]}
        result["mentor"].extend(candidate_item(row, request) for row in mentor_rows if row["id"] not in seen)
    if len(result["space"]) < 3:
        seen = {item["id"] for item in result["space"]}
        result["space"].extend(candidate_item(row, request) for row in space_rows if row["id"] not in seen)
    result["mentor"] = result["mentor"][:2]
    result["space"] = result["space"][:3]
    return {"request_id": cursor.lastrowid, "request": {**request.model_dump(), "neighborhood": NEIGHBORHOOD}, "results": result}
@app.post("/api/learning-requests")
def create_learning_request(data: LearningRequestInput):
    with get_db() as conn:
        user = conn.execute("SELECT id FROM users WHERE id=? AND role='learner'", (data.user_id,)).fetchone()
        mentor = conn.execute("SELECT id FROM candidates WHERE id=? AND kind='mentor'", (data.mentor_id,)).fetchone()
        space = conn.execute("SELECT id FROM candidates WHERE id=? AND kind='space'", (data.space_id,)).fetchone()
        if not user or not mentor or not space: raise HTTPException(400, "선택한 멘토와 학습 공간을 다시 확인해 주세요.")
        pending = conn.execute("SELECT id FROM learning_requests WHERE user_id=? AND status='pending' LIMIT 1", (data.user_id,)).fetchone()
        if pending:
            raise HTTPException(400, "대기중인 멘토 요청이 있어 수락·거절·취소 전에는 새 멘토 요청을 보낼 수 없습니다.")
        cursor = conn.execute("INSERT INTO learning_requests (user_id,mentor_id,space_id) VALUES (?,?,?)", (data.user_id, data.mentor_id, data.space_id))
    return {"id": cursor.lastrowid, "status": "pending"}
@app.post("/api/learning-requests/{request_id}/complete")
def complete_learning_request(request_id: int, data: LearningRequestInput):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM learning_requests WHERE id=? AND user_id=?", (request_id, data.user_id)).fetchone()
        if not row: raise HTTPException(404, "요청 기록을 찾지 못했습니다.")
        conn.execute("UPDATE learning_requests SET status='completed', completed_at=CURRENT_TIMESTAMP WHERE id=?", (request_id,))
    return {"ok": True, "status": "completed"}
@app.post("/api/saved")
def save_candidate(data: SaveInput):
    with get_db() as conn: conn.execute("INSERT OR IGNORE INTO saved_candidates (user_id,candidate_id) VALUES (?,?)", (data.user_id, data.candidate_id))
    return {"ok": True}
@app.post("/api/reviews")
def add_review(data: ReviewInput):
    if not data.content.strip(): raise HTTPException(400, "후기 내용을 입력해 주세요.")
    with get_db() as conn:
        request = conn.execute("SELECT * FROM learning_requests WHERE id=? AND user_id=? AND status='completed'", (data.request_id, data.user_id)).fetchone()
        if not request: raise HTTPException(400, "학습을 마친 뒤에만 이용 후기를 남길 수 있습니다.")
        conn.execute("INSERT INTO reviews (user_id,candidate_id,request_id,content) VALUES (?,?,?,?)", (data.user_id, request["mentor_id"], data.request_id, data.content.strip()))
    return {"ok": True}
@app.get("/api/history/{user_id}")
def history(user_id: int):
    with get_db() as conn:
        saved = conn.execute("SELECT c.* FROM saved_candidates s JOIN candidates c ON c.id=s.candidate_id WHERE s.user_id=? ORDER BY s.id DESC", (user_id,)).fetchall()
        requests = conn.execute("""SELECT lr.*, m.name AS mentor_name, s.name AS space_name, m.official_url AS mentor_url
            FROM learning_requests lr JOIN candidates m ON m.id=lr.mentor_id JOIN candidates s ON s.id=lr.space_id
            WHERE lr.user_id=? ORDER BY lr.id DESC""", (user_id,)).fetchall()
        reviews = conn.execute("SELECT r.*, c.name FROM reviews r JOIN candidates c ON c.id=r.candidate_id WHERE r.user_id=? ORDER BY r.id DESC", (user_id,)).fetchall()
    return {"saved": [candidate_item(row) for row in saved], "requests": [dict(row) for row in requests], "reviews": [dict(row) for row in reviews]}
@app.get("/api/mentor/{user_id}")
def mentor_profile(user_id: int):
    with get_db() as conn: row = conn.execute("SELECT * FROM candidates WHERE mentor_user_id=? LIMIT 1", (user_id,)).fetchone()
    return candidate_item(row) if row else None
@app.put("/api/mentor")
def update_mentor(data: MentorProfile):
    if not data.tools or not data.times: raise HTTPException(400, "가능 도구와 가능 시간을 선택해 주세요.")
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=? AND role='mentor'", (data.user_id,)).fetchone()
        if not user: raise HTTPException(403, "멘토 계정만 수정할 수 있습니다.")
        verification_status = 'pending'
        row = conn.execute("SELECT id FROM candidates WHERE mentor_user_id=?", (data.user_id,)).fetchone()
        if row:
            conn.execute("UPDATE candidates SET tools=?, times=?, consent_confirmed=?, verification_status='pending', source_date=? WHERE id=?", (",".join(data.tools), ",".join(data.times), int(data.consent_confirmed), "2026-11-01", row["id"]))
        else:
            conn.execute("INSERT INTO candidates (kind,name,tools,levels,devices,regions,times,official_url,source,source_date,description,distance,neighborhood,mentor_user_id,consent_confirmed,verification_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ("mentor", user["nickname"] + " 멘토", ",".join(data.tools), "입문,초급,중급", "스마트폰,노트북,태블릿", "천안시 서북구", ",".join(data.times), "https://www.cheonan.go.kr/", "멘토가 직접 입력한 안내", "2026-11-01", "수강 전 공식 안내 페이지에서 운영 정보를 확인해 주세요.", "불당동 인근", NEIGHBORHOOD, data.user_id, int(data.consent_confirmed), "pending"))
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
@app.post("/api/team/mentors/{user_id}/consent")
def confirm_mentor_consent(user_id: int, x_team_password: str | None = Header(default=None)):
    require_team_password(x_team_password)
    with get_db() as conn:
        mentor = conn.execute("SELECT * FROM users WHERE id=? AND role='mentor'", (user_id,)).fetchone()
        if not mentor:
            raise HTTPException(404, "멘토 계정을 찾지 못했습니다.")
        conn.execute("UPDATE users SET mentor_consent_confirmed=1 WHERE id=?", (user_id,))
        conn.execute("UPDATE candidates SET consent_confirmed=1 WHERE mentor_user_id=?", (user_id,))
    return {"ok": True, "consent_confirmed": True}
@app.post("/api/team/mentors/{user_id}/verify")
def verify_mentor(user_id: int, x_team_password: str | None = Header(default=None)):
    require_team_password(x_team_password)
    with get_db() as conn:
        mentor = conn.execute("SELECT * FROM users WHERE id=? AND role='mentor'", (user_id,)).fetchone()
        candidate = conn.execute("SELECT * FROM candidates WHERE mentor_user_id=?", (user_id,)).fetchone()
        if not mentor or not candidate:
            raise HTTPException(404, "멘토 프로필을 찾지 못했습니다.")
        if not mentor["mentor_consent_confirmed"]:
            raise HTTPException(400, "동의함으로 표시된 멘토만 확인됨으로 변경할 수 있습니다.")
        conn.execute("UPDATE users SET mentor_verification_status='verified' WHERE id=?", (user_id,))
        conn.execute("UPDATE candidates SET verification_status='verified' WHERE mentor_user_id=?", (user_id,))
    return {"ok": True, "verification_status": "verified"}
@app.get("/api/mentor-requests/{user_id}")
def mentor_requests(user_id: int):
    with get_db() as conn:
        mentor = conn.execute("SELECT id FROM candidates WHERE mentor_user_id=? AND kind='mentor'", (user_id,)).fetchone()
        if not mentor:
            return []
        rows = conn.execute("""SELECT lr.*, u.nickname AS learner_name, s.name AS space_name
            FROM learning_requests lr JOIN users u ON u.id=lr.user_id JOIN candidates s ON s.id=lr.space_id
            WHERE lr.mentor_id=? ORDER BY lr.id DESC""", (mentor["id"],)).fetchall()
    return [dict(row) for row in rows]
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

# --- 배포용: 빌드된 화면(dist)을 백엔드가 같이 서빙 ---
from fastapi.staticfiles import StaticFiles
_dist_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dist")
if os.path.isdir(_dist_dir):
    app.mount("/", StaticFiles(directory=_dist_dir, html=True), name="static")
