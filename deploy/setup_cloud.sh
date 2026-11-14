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
#   5) 서버를 시스템 서비스로 등록 (서버 안쪽 8000번), 꺼지거나 재부팅돼도 자동으로 다시 켜짐
#   6) https: Caddy가 80·443에서 받아 8000번으로 넘김. 인증서는 Caddy가 자동 발급·갱신
#      주소 이름은 /etc/itda-ai.env의 SITE_DOMAIN (기본: 공인IP를 하이픈으로 바꾼 <ip>.sslip.io)
#   7) 방화벽에서 80·443 열기, 마지막에 정상 동작 확인
set -euo pipefail

REPO_URL="https://github.com/ebook1318-dev/itda-ai.git"
APP_DIR="/opt/itda-ai"
ENV_FILE="/etc/itda-ai.env"
SERVICE="itda-ai"
PORT=8000            # 서버 안쪽에서만 쓰는 포트 (밖에서는 Caddy가 80·443으로 받음)
CADDY_VERSION="2.8.4"

step() { printf '\n\033[1;34m[%s] %s\033[0m\n' "$1" "$2"; }
ok()   { printf '\033[1;32m  ✔ %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m  ! %s\033[0m\n' "$1"; }

if [ "$(id -u)" -ne 0 ]; then echo "root 계정으로 실행해 주세요."; exit 1; fi

step 1/7 "프로그램 설치 (처음에는 3~5분 걸려요)"
if ! command -v python3.11 >/dev/null 2>&1; then
  dnf install -y python3.11 python3.11-pip >/dev/null
fi
ok "$(python3.11 --version)"
if ! command -v node >/dev/null 2>&1 || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 18 ]; then
  # 서버의 프로그램 목록(dnf)에 Node 20이 없을 수 있어서, Node 공식 사이트에서 직접 받습니다.
  NODE_VERSION="v20.18.1"
  case "$(uname -m)" in x86_64) NODE_ARCH=x64 ;; aarch64) NODE_ARCH=arm64 ;; *) echo "지원하지 않는 CPU: $(uname -m)"; exit 1 ;; esac
  command -v xz >/dev/null 2>&1 || dnf install -y xz >/dev/null
  curl -fsSL "https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-linux-$NODE_ARCH.tar.xz" -o /tmp/node.tar.xz
  rm -rf /usr/local/lib/nodejs && mkdir -p /usr/local/lib/nodejs
  tar -xJf /tmp/node.tar.xz -C /usr/local/lib/nodejs --strip-components=1
  ln -sf /usr/local/lib/nodejs/bin/node /usr/local/bin/node
  ln -sf /usr/local/lib/nodejs/bin/npm /usr/local/bin/npm
  ln -sf /usr/local/lib/nodejs/bin/npx /usr/local/bin/npx
  rm -f /tmp/node.tar.xz
  hash -r
fi
ok "Node $(node --version)"
command -v git >/dev/null 2>&1 || dnf install -y git >/dev/null
ok "$(git --version)"

step 2/7 "코드 받기 (GitHub 최신)"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch -q origin main
  git -C "$APP_DIR" reset -q --hard origin/main
else
  git clone -q --depth 1 "$REPO_URL" "$APP_DIR"
fi
ok "$(git -C "$APP_DIR" log -1 --format='%h %s')"

step 3/7 "부품 설치 · 화면 빌드 (1~3분)"
cd "$APP_DIR"
[ -d .venv ] || python3.11 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
ok "파이썬 부품 설치"
npm ci --no-audit --no-fund --loglevel=error
npm run build --silent >/dev/null
ok "화면 빌드 (dist)"

step 4/7 "비밀 설정"
if [ ! -f "$ENV_FILE" ]; then
  echo "  Render의 Environment 화면에 있는 값과 같은 값을 넣으면 돼요."
  echo "  붙여넣기는 마우스 오른쪽 클릭. 입력해도 화면에 안 보이는 게 정상이에요."
  ask() { local name="$1" label="$2" value=""; while [ -z "$value" ]; do read -r -s -p "  $label: " value < /dev/tty; echo; done; printf '%s=%s\n' "$name" "$value" >> "$ENV_FILE.tmp"; }
  : > "$ENV_FILE.tmp"; chmod 600 "$ENV_FILE.tmp"
  ask TEAM_PASSWORD      "팀 비밀번호 (TEAM_PASSWORD)"
  ask TURSO_DATABASE_URL "Turso 주소 (TURSO_DATABASE_URL, libsql://로 시작)"
  ask TURSO_AUTH_TOKEN   "Turso 토큰 (TURSO_AUTH_TOKEN)"
  ask ANTHROPIC_API_KEY  "AI 팀 키 (ANTHROPIC_API_KEY)"
  {
    echo "# 메일 알림을 켜려면 아래 두 줄의 # 을 지우고 값을 넣은 뒤: systemctl restart $SERVICE"
    echo "# BREVO_API_KEY="
    echo "# MAIL_FROM="
  } >> "$ENV_FILE.tmp"
  mv "$ENV_FILE.tmp" "$ENV_FILE"
  ok "저장: $ENV_FILE (root만 읽을 수 있음)"
else
  ok "이미 있음: $ENV_FILE (바꾸려면 파일을 지우고 다시 실행)"
fi
# 나중에 추가된 비밀 값: 없으면 이번에 한 번만 물어봐요.
if ! grep -q '^DEMO_MENTOR_PASSWORD=' "$ENV_FILE"; then
  echo "  [새 설정] 예시 멘토 5명(캔바장인 등)이 로그인할 때 쓸 새 비밀번호를 정해 주세요."
  echo "  8자 이상 · 영어와 숫자를 섞어서. 예전 비밀번호(itda2026)는 쓰지 마세요. 화면에 안 보이는 게 정상이에요."
  value=""
  while [ "${#value}" -lt 8 ] || [ "$value" = "itda2026" ]; do read -r -s -p "  예시 멘토 비밀번호: " value < /dev/tty; echo; done
  printf 'DEMO_MENTOR_PASSWORD=%s\n' "$value" >> "$ENV_FILE"; unset value
  ok "예시 멘토 비밀번호 저장"
fi
if ! grep -q '^TEAM_NOTIFY_EMAIL=' "$ENV_FILE"; then
  echo "  [새 설정] 새 멘토가 활동 정보를 저장하면 확인 요청 메일을 받을 '팀 메일 주소'를 적어 주세요."
  echo "  (메일 주소를 붙여넣고 Enter. 지금 정하지 않으려면 그냥 Enter)"
  read -r -p "  팀 알림 메일: " value < /dev/tty
  printf 'TEAM_NOTIFY_EMAIL=%s\n' "$(echo "$value" | tr -d '[:space:]')" >> "$ENV_FILE"; unset value
  ok "팀 알림 메일 설정 (바꾸려면 $ENV_FILE 의 TEAM_NOTIFY_EMAIL 줄 수정 후 systemctl restart $SERVICE)"
fi

step 5/7 "서비스 등록 (자동 실행)"
cat > "/etc/systemd/system/$SERVICE.service" <<UNIT
[Unit]
Description=Baeumitda AI web service
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port $PORT --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable -q "$SERVICE"
systemctl restart "$SERVICE"
ok "서비스 시작"

step 6/7 "https 설정 (Caddy)"
IP="$(curl -s -m 5 ifconfig.me || true)"
if ! grep -q '^SITE_DOMAIN=' "$ENV_FILE"; then
  echo "SITE_DOMAIN=${IP//./-}.sslip.io" >> "$ENV_FILE"
fi
DOMAIN="$(grep '^SITE_DOMAIN=' "$ENV_FILE" | tail -1 | cut -d= -f2-)"
# 메일 속 바로가기 주소도 https 주소로 맞춤
sed -i '/^SITE_URL=/d' "$ENV_FILE"; echo "SITE_URL=https://$DOMAIN" >> "$ENV_FILE"
if ! /usr/local/bin/caddy version 2>/dev/null | grep -q "v$CADDY_VERSION"; then
  case "$(uname -m)" in x86_64) CADDY_ARCH=amd64 ;; aarch64) CADDY_ARCH=arm64 ;; esac
  curl -fsSL "https://github.com/caddyserver/caddy/releases/download/v$CADDY_VERSION/caddy_${CADDY_VERSION}_linux_${CADDY_ARCH}.tar.gz" -o /tmp/caddy.tar.gz
  tar -xzf /tmp/caddy.tar.gz -C /usr/local/bin caddy && rm -f /tmp/caddy.tar.gz
  chmod +x /usr/local/bin/caddy
fi
ok "$(/usr/local/bin/caddy version | cut -d' ' -f1)"
mkdir -p /etc/caddy /var/lib/caddy
cat > /etc/caddy/Caddyfile <<CADDY
$DOMAIN {
	encode gzip
	reverse_proxy 127.0.0.1:$PORT
}
http://${IP:-127.0.0.1} {
	redir https://$DOMAIN{uri} permanent
}
CADDY
cat > /etc/systemd/system/caddy.service <<UNIT
[Unit]
Description=Caddy web server (https for $SERVICE)
After=network-online.target $SERVICE.service
Wants=network-online.target

[Service]
Environment=XDG_DATA_HOME=/var/lib XDG_CONFIG_HOME=/etc
ExecStart=/usr/local/bin/caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
ExecReload=/usr/local/bin/caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl restart "$SERVICE"
systemctl enable -q caddy
systemctl restart caddy
ok "주소: https://$DOMAIN"

step 7/7 "방화벽 · 동작 확인"
if systemctl is-active -q firewalld; then
  firewall-cmd -q --permanent --add-service=http --add-service=https
  firewall-cmd -q --reload
  ok "방화벽 80·443 열기"
else
  ok "서버 방화벽 꺼져 있음 (클라우드의 노출 포트 설정을 따름)"
fi
rm -f /tmp/itda-health
for i in $(seq 1 60); do
  if curl -fs -m 2 "http://127.0.0.1:$PORT/api/health" >/tmp/itda-health 2>/dev/null; then break; fi
  sleep 1
done
if [ ! -s /tmp/itda-health ]; then
  warn "서버 프로그램이 응답하지 않아요. 아래 줄을 붙여넣고 결과를 보여주세요:"
  echo "  journalctl -u $SERVICE -n 40 --no-pager"
  exit 1
fi
ok "서버 프로그램 응답: $(cat /tmp/itda-health)"
echo "  https 인증서를 받는 중이에요 (최대 1~2분)..."
HTTPS_OK=""
for i in $(seq 1 24); do
  if curl -fs -m 5 "https://$DOMAIN/api/health" >/dev/null 2>&1; then HTTPS_OK=1; break; fi
  sleep 5
done
if [ -n "$HTTPS_OK" ]; then
  ok "https 연결 확인"
  printf '\n\033[1;32m완료! 브라우저에서 접속해 보세요: https://%s\033[0m\n' "$DOMAIN"
  echo "AI 확인: 사이트 로고 5번 → 팀 비밀번호 → 'AI 연결 확인'"
else
  warn "https 인증서를 아직 못 받았어요. 아래 줄을 붙여넣고 결과를 보여주세요:"
  echo "  journalctl -u caddy -n 40 --no-pager"
  exit 1
fi
