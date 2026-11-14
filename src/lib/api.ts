// 로그인 출입증(토큰)을 모든 요청에 자동으로 붙입니다. 서버는 이 토큰으로 누구인지 판단해요.
const USER_KEY = 'learning-link-user'
export const AUTH_EXPIRED_EVENT = 'itda-auth-expired'

function savedToken(): string {
  try { return JSON.parse(window.localStorage.getItem(USER_KEY) || 'null')?.token || '' } catch { return '' }
}

export const api = async (path: string, init?: RequestInit) => {
  const clean = path.replace(/^\/+/, '')
  const token = savedToken()
  const headers = new Headers(init?.headers)
  if (token && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(import.meta.env.BASE_URL + 'api/' + clean, { ...init, headers })
  // 출입증이 만료됐거나 지워졌으면 화면에 알려서 다시 로그인하게 합니다. (로그인 실패·팀 비밀번호 오류는 제외)
  if (response.status === 401 && token && !clean.startsWith('auth/') && !clean.startsWith('team/')) {
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
  }
  return response
}
