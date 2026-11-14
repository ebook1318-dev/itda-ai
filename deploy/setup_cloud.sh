#!/usr/bin/env bash
# 배움잇다 AI — 모두의 AI 클라우드(NAVER, Rocky Linux 8) 설치·업데이트 스크립트
#
# 처음 설치와 업데이트 모두 이 스크립트 하나로 합니다. 다시 실행하면 GitHub 최신 코드로 업데이트됩니다.
#   curl -fsSLo setup.sh https://raw.githubusercontent.com/ebook1318-dev/itda-ai/main/deploy/setup_cloud.sh
#   bash setup.sh
#
# 하는 일
#   1) Python 3.11 · Node 20 · git 설치 (이미 있으면 건너뜀)
#   2) GitHub에서 코드 받기 (/opt/itda-ai) — 이미 있으면 최신으로 업데이트
#   3) 파이썬 부품 설치, 화면(React) 빌드
#   4) 비밀 설정 파일(/etc/itda-ai.env) — 처음 한 번만 물어봄 (입력값은 화면에 안 보임)
#   5) 서버를 시스템 서비스로 등록: 80번 포트, 꺼지거나 재부팅돼도 자동으로 다시 켜짐
#   6) 방화벽에서 80·443 열기, 마지막에 정상 동작 확인
set -euo pipefail

REPO_URL="https://github.com/ebook1318-dev/itda-ai.git"
APP_DIR="/opt/itda-ai"
ENV_FILE="/etc/itda-ai.env"
SERVICE="itda-ai"
PORT=80

step() { printf '\n\033[1;34m[%s] %s\033[0m\n' "$1" "$2"; }
ok()   { printf '\033[1;32m  ✔ %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m  ! %s\033[0m\n' "$1"; }

if [ "$(id -u)" -ne 0 ]; then echo "root 계정으로 실행해 주세요."; exit 1; fi

step 1/6 "프로그램 설치 (처음에는 3~5분 걸려요)"
if ! command -v python3.11 >/dev/null 2>&1; then
  dnf install -y python3.11 python3.11-pip >/dev/null
fi
ok "$(python3.11 --version)"
if ! command -v node >/dev/null 2>&1 || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 18 ]; then
  dnf module reset -y nodejs >/dev/null 2>&1 || true
  dnf module enable -y nodejs:20 >/dev/null
  dnf install -y nodejs >/dev/null
fi
ok "Node $(node --version)"
command -v git >/dev/null 2>&1 || dnf install -y git >/dev/null
ok "$(git --version)"

step 2/6 "코드 받기 (GitHub 최신)"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch -q origin main
  git -C "$APP_DIR" reset -q --hard origin/main
else
  git clone -q --depth 1 "$REPO_URL" "$APP_DIR"
fi
ok "$(git -C "$APP_DIR" log -1 --format='%h %s')"

step 3/6 "부품 설치 · 화면 빌드 (1~3분)"
cd "$APP_DIR"
[ -d .venv ] || python3.11 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
ok "파이썬 부품 설치"
npm ci --no-audit --no-fund --loglevel=error
npm run build --silent >/dev/null
ok "화면 빌드 (dist)"

step 4/6 "비밀 설정"
if [ ! -f "$ENV_FILE" ]; then
  echo "  Render의 Environment 화면에 있는 값과 같은 값을 넣으면 돼요."
  echo "  붙여넣기는 마우스 오른쪽 클릭. 입력해도 화면에 안 보이는 게 정상이에요."
  ask() { local name="$1" label="$2" value=""; while [ -z "$value" ]; do read -r -s -p "  $label: " value < /dev/tty; echo; done; printf '%s=%s\n' "$name" "$value" >> "$ENV_FILE.tmp"; }
  : > "$ENV_FILE.tmp"; chmod 600 "$ENV_FILE.tmp"
  ask TEAM_PASSWORD      "팀 비밀번호 (TEAM_PASSWORD)"
  ask TURSO_DATABASE_URL "Turso 주소 (TURSO_DATABASE_URL, libsql://로 시작)"
  ask TURSO_AUTH_TOKEN   "Turso 토큰 (TURSO_AUTH_TOKEN)"
  ask ANTHROPIC_API_KEY  "AI 팀 키 (ANTHROPIC_API_KEY)"
  IP="$(curl -s -m 5 ifconfig.me || true)"
  {
    echo "SITE_URL=http://${IP:-localhost}"
    echo "# 메일 알림을 켜려면 아래 두 줄의 # 을 지우고 값을 넣은 뒤: systemctl restart $SERVICE"
    echo "# BREVO_API_KEY="
    echo "# MAIL_FROM="
  } >> "$ENV_FILE.tmp"
  mv "$ENV_FILE.tmp" "$ENV_FILE"
  ok "저장: $ENV_FILE (root만 읽을 수 있음)"
else
  ok "이미 있음: $ENV_FILE (바꾸려면 파일을 지우고 다시 실행)"
fi

step 5/6 "서비스 등록 (자동 실행)"
cat > "/etc/systemd/system/$SERVICE.service" <<UNIT
[Unit]
Description=Baeumitda AI web service
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port $PORT --proxy-headers
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable -q "$SERVICE"
systemctl restart "$SERVICE"
ok "서비스 시작"

step 6/6 "방화벽 · 동작 확인"
if systemctl is-active -q firewalld; then
  firewall-cmd -q --permanent --add-service=http --add-service=https
  firewall-cmd -q --reload
  ok "방화벽 80·443 열기"
else
  ok "서버 방화벽 꺼져 있음 (클라우드의 노출 포트 설정을 따름)"
fi
for i in $(seq 1 60); do
  if curl -fs -m 2 "http://127.0.0.1:$PORT/api/health" >/tmp/itda-health 2>/dev/null; then break; fi
  sleep 1
done
if [ -s /tmp/itda-health ]; then
  ok "서버 응답: $(cat /tmp/itda-health)"
  IP="$(curl -s -m 5 ifconfig.me || echo '공인IP')"
  printf '\n\033[1;32m완료! 브라우저에서 접속해 보세요: http://%s\033[0m\n' "$IP"
  echo "AI 확인: 사이트 로고 5번 → 팀 비밀번호 → 'AI 연결 확인'"
else
  warn "서버가 응답하지 않아요. 아래 줄을 붙여넣고 결과를 보여주세요:"
  echo "  journalctl -u $SERVICE -n 40 --no-pager"
  exit 1
fi
