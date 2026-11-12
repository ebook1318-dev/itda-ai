"""Turso(클라우드 SQLite) 연결 — 기존 sqlite3 코드를 거의 그대로 쓸 수 있게 만든 얇은 호환층.

왜 필요한가: Render 무료 서버는 재시작·잠자기 때마다 디스크가 초기화돼서 data/app.db가 사라집니다.
Turso에 저장하면 서버가 다시 켜져도 가입·요청·후기 데이터가 그대로 남습니다.

방식: Turso HTTP API(/v2/pipeline)를 표준 라이브러리(http.client)로 호출합니다. 추가 설치 패키지 없음.
지원 범위(이 앱이 쓰는 것만): execute(), executescript(), fetchone/fetchall, lastrowid, rowcount,
row["컬럼"] · row[0] · dict(row), `with conn:` 문, UNIQUE 위반 → sqlite3.IntegrityError.
각 문장은 자동 커밋됩니다(이 앱은 여러 문장을 하나의 트랜잭션으로 묶을 필요가 없음).
"""
import base64
import http.client
import json
import sqlite3
import threading
import urllib.parse

class Row:
    """sqlite3.Row처럼 row["name"], row[0], dict(row) 모두 되게 하는 행 객체."""
    __slots__ = ("_cols", "_values", "_index")
    def __init__(self, cols, values):
        self._cols, self._values = cols, values
        self._index = {name: i for i, name in enumerate(cols)}
    def keys(self):
        return list(self._cols)
    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._values[key]
        return self._values[self._index[key]]
    def __iter__(self):
        return iter(self._values)
    def __len__(self):
        return len(self._values)
    def __repr__(self):
        return f"Row({dict(zip(self._cols, self._values))})"

class Cursor:
    def __init__(self, cols=(), rows=(), lastrowid=None, rowcount=-1):
        self.description = [(name, None, None, None, None, None, None) for name in cols] or None
        self._rows = list(rows)
        self.lastrowid = lastrowid
        self.rowcount = rowcount
    def fetchone(self):
        return self._rows.pop(0) if self._rows else None
    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows
    def __iter__(self):
        return iter(self.fetchall())

def _encode(value):
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": str(int(value))}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    if isinstance(value, (bytes, bytearray)):
        return {"type": "blob", "base64": base64.b64encode(bytes(value)).decode()}
    return {"type": "text", "value": str(value)}

def _decode(cell):
    kind = cell.get("type")
    if kind == "null":
        return None
    if kind == "integer":
        return int(cell["value"])
    if kind == "float":
        return float(cell["value"])
    if kind == "blob":
        return base64.b64decode(cell.get("base64", ""))
    return cell.get("value")

def _split_script(script):
    """executescript용: 세미콜론 기준으로 완성된 SQL 문장만 잘라냅니다 (문자열 안의 ;는 안전)."""
    statements, buffer = [], ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            if buffer.strip():
                statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        statements.append(buffer.strip())
    return statements

class TursoClient:
    """서버 프로세스 하나에 하나. 스레드마다 HTTPS 연결을 재사용해 왕복 시간을 줄입니다."""
    def __init__(self, url, token, timeout=15):
        url = url.strip()
        if url.startswith("libsql://"):
            url = "https://" + url[len("libsql://"):]
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("https", "http") or not parsed.hostname:
            raise ValueError("TURSO_DATABASE_URL 형식이 올바르지 않습니다 (libsql://... 이어야 함).")
        self.scheme, self.host, self.port = parsed.scheme, parsed.hostname, parsed.port
        self.token, self.timeout = token.strip(), timeout
        self._local = threading.local()

    def _connection(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            cls = http.client.HTTPSConnection if self.scheme == "https" else http.client.HTTPConnection
            conn = cls(self.host, self.port, timeout=self.timeout)
            self._local.conn = conn
        return conn

    def pipeline(self, statements):
        """[(sql, params), ...]를 한 번의 요청으로 실행하고 결과 목록을 돌려줍니다."""
        requests = [{"type": "execute", "stmt": {"sql": sql, "args": [_encode(v) for v in params], "want_rows": True}} for sql, params in statements]
        requests.append({"type": "close"})
        body = json.dumps({"requests": requests}).encode("utf-8")
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": "itda-ai/1.0"}
        for attempt in (1, 2):  # 끊긴 keep-alive 연결이면 한 번 새로 연결해서 재시도
            conn = self._connection()
            try:
                conn.request("POST", "/v2/pipeline", body=body, headers=headers)
                resp = conn.getresponse()
                raw = resp.read()
                break
            except (http.client.HTTPException, ConnectionError, OSError):
                conn.close()
                self._local.conn = None
                if attempt == 2:
                    raise
        if resp.status != 200:
            raise sqlite3.OperationalError(f"Turso 응답 오류 {resp.status}: {raw[:300].decode('utf-8', 'replace')}")
        results = json.loads(raw.decode("utf-8"))["results"]
        out = []
        for (sql, _), result in zip(statements, results):
            if result.get("type") == "error":
                error = result.get("error", {})
                code, message = str(error.get("code") or ""), str(error.get("message") or "")
                if code.startswith("SQLITE_CONSTRAINT") or "constraint failed" in message.lower():
                    raise sqlite3.IntegrityError(message)
                raise sqlite3.OperationalError(f"{message} [{code}] — {sql[:120]}")
            res = result["response"]["result"]
            cols = [col.get("name") or "" for col in res.get("cols", [])]
            rows = [Row(cols, [_decode(cell) for cell in row]) for row in res.get("rows", [])]
            last = res.get("last_insert_rowid")
            out.append(Cursor(cols, rows, int(last) if last is not None else None, res.get("affected_row_count", -1)))
        return out

class TursoConnection:
    """get_db()가 돌려주는 연결. sqlite3.Connection처럼 쓰면 됩니다."""
    row_factory = None  # sqlite3 코드와의 호환용 (행은 항상 Row로 돌려줌)
    def __init__(self, client):
        self._client = client
    def execute(self, sql, params=()):
        return self._client.pipeline([(sql, tuple(params))])[0]
    def batch(self, statements):
        """[(sql, params), ...]를 한 번의 요청으로 실행합니다."""
        return self._client.pipeline([(sql, tuple(params)) for sql, params in statements]) if statements else []
    def executescript(self, script):
        statements = _split_script(script)
        if statements:
            self._client.pipeline([(sql, ()) for sql in statements])
        return Cursor()
    def commit(self):
        pass  # 문장마다 자동 커밋
    def rollback(self):
        pass
    def close(self):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        return False
