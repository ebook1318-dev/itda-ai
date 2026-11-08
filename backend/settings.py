import os

# 비밀번호를 코드에 직접 쓰지 않습니다 (깃허브가 공개 저장소라 그대로 노출됨).
# 반드시 Render 대시보드의 Environment 탭에서 TEAM_PASSWORD 값을 설정해야
# 관리자(멘토 확인 상태 관리) 화면에 접근할 수 있습니다. 값이 없으면 접근이 막힙니다.
TEAM_PASSWORD = os.getenv("TEAM_PASSWORD", "")
