export type FormValues = { tool: string; course_name?: string; level: string; devices: string[]; time_slots: string[]; neighborhoods: string[]; keyword?: string }
export type User = { id: number; nickname: string; role: 'learner' | 'mentor' }
export type MatchTier = 'match' | 'partial' | 'miss'
export type MatchDetailField = { tier: MatchTier; label: string }
export type MatchDetail = { tool?: MatchDetailField; level?: MatchDetailField; device: MatchDetailField; time: MatchDetailField; neighborhood: MatchDetailField; keyword?: MatchDetailField }
export type Candidate = { id: number; kind: 'mentor' | 'space'; name: string; tools: string[]; levels: string[]; devices: string[]; regions: string[]; times: string[]; official_url: string; source: string; source_date: string; description: string; score: number; match_percent: number | null; match_detail: MatchDetail | Record<string, never>; reason: string; ai_reason?: string; distance: string; neighborhood: string; neighborhoods: string[]; consent_confirmed: boolean; verification_status: 'pending' | 'verified' | 'not_applicable'; facility?: string; operating_hours?: string; usage_procedure?: string; lat?: number; lng?: number; topics?: string[] }
export type ResultData = { request_id: number; request: FormValues & { neighborhood: string }; results: { mentor: Candidate[]; space: Candidate[] } }
export type Purpose = { label: string; tool: string; subtopics: { label: string; example: string }[] }
export const purposes: Purpose[] = [
  { label: '문서·글쓰기', tool: 'ChatGPT', subtopics: [{ label: '안내문 쓰기', example: '행사 안내문을 알기 쉽게 작성하고 싶어요' }, { label: '자기소개·지원 글', example: '나를 소개하는 글을 자연스럽게 쓰고 싶어요' }, { label: '회의·학습 정리', example: '회의나 학습 내용을 보기 좋게 정리하고 싶어요' }] },
  { label: '사진·영상 편집', tool: '캡컷', subtopics: [{ label: '사진 꾸미기', example: '사진을 보기 좋게 다듬고 싶어요' }, { label: '짧은 영상 만들기', example: '사진이나 영상을 편집하고 싶어요' }, { label: '자막 넣기', example: '영상에 읽기 쉬운 자막을 넣고 싶어요' }] },
  { label: '홍보물·디자인', tool: '캔바', subtopics: [{ label: '행사 홍보물', example: '행사 안내 홍보물을 만들고 싶어요' }, { label: '카드뉴스', example: '핵심 내용을 담은 카드뉴스를 만들고 싶어요' }, { label: '발표자료', example: '보기 쉬운 발표자료를 만들고 싶어요' }] },
]
export const courses = [
  { purpose: '문서·글쓰기', name: 'AI로 글쓰기 첫걸음', tool: 'ChatGPT', text: '안내문, 자기소개, 여행 계획처럼 생활에 필요한 글을 쉽게 써볼 수 있어요.' },
  { purpose: '사진·영상 편집', name: '스마트폰 영상 만들기', tool: '캡컷', text: '사진과 짧은 영상을 이어 붙이고 자막을 넣어볼 수 있어요.' },
  { purpose: '홍보물·디자인', name: '나만의 홍보물 만들기', tool: '캔바', text: '행사 안내문과 카드뉴스를 보기 좋게 꾸며볼 수 있어요.' },
]
