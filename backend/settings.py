import os

# 비밀번호를 코드에 직접 쓰지 않습니다 (깃허브가 공개 저장소라 그대로 노출됨).
# 반드시 Render 대시보드의 Environment 탭에서 TEAM_PASSWORD 값을 설정해야
# 관리자(멘토 확인 상태 관리) 화면에 접근할 수 있습니다. 값이 없으면 접근이 막힙니다.
TEAM_PASSWORD = os.getenv("TEAM_PASSWORD", "")

# 예시 멘토 5명(챗지피티쌤·영상노트·캔바장인·자소서멘토·자막요정)의 로그인 비밀번호.
# 공개 저장소라 코드에 쓰지 않고 서버 비밀 설정에만 넣습니다. 비어 있으면 예시 멘토로는 로그인할 수 없어요.
DEMO_MENTOR_PASSWORD = os.getenv("DEMO_MENTOR_PASSWORD", "")
