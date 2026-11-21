import { Candidate, MatchTier } from '../data'
import Avatar from './Avatar'
type Props = {
  title: string
  items: Candidate[]
  selected?: Candidate | null
  onSelect: (candidate: Candidate) => void
  onSkip?: () => void
  skipped?: boolean
  aiRanked?: boolean
  kind?: 'mentor' | 'space'
}
function tierFromPercent(percent: number): MatchTier {
  return percent >= 70 ? 'match' : percent >= 45 ? 'partial' : 'miss'
}
function MatchBadge({ item }: { item: Candidate }) {
  if (item.match_percent === null || item.match_percent === undefined) return null
  return <span className={`match-badge tier-${tierFromPercent(item.match_percent)}`}>일치도 <b>{item.match_percent}%</b></span>
}
const TIER_MARK = { match: '✓', partial: '○', miss: '−', neutral: '·' } as const
function MetaChips({ item }: { item: Candidate }) {
  const detail = item.match_detail
  if (!detail || !('device' in detail)) return null
  // 공간(도서관·학습관 등)은 특정 도구·수준을 가르치지 않는 장소라, 도구·수준 배지는 멘토에게만 보여줍니다.
  const rows: { key: keyof typeof detail; label: string }[] = item.kind === 'space'
    ? [{ key: 'device', label: '기기' }, { key: 'time', label: '시간' }, { key: 'neighborhood', label: '동' }]
    : [{ key: 'tool', label: '도구' }, { key: 'keyword', label: '학습내용' }, { key: 'level', label: '수준' }, { key: 'device', label: '기기' }, { key: 'time', label: '시간' }, { key: 'neighborhood', label: '동' }]
  return <div className="meta">{rows.map(row => {
    const field = detail[row.key]
    if (!field) return null
    // 학습내용이 멘토 주제와 겹치지 않으면, 수강생이 쓴 글을 그대로 되풀이하지 않고 숨깁니다 (AI 추천 이유에서 설명)
    if (row.key === 'keyword' && field.tier === 'miss') return null
    const tier = field.tier
    return <span className={`meta-item ${tier}`} key={row.key}><span className="mark" aria-hidden="true">{TIER_MARK[tier as keyof typeof TIER_MARK]}</span><b>{row.label}</b> {field.label}</span>
  })}</div>
}
function RecommendReason({ item }: { item: Candidate }) {
  if (item.ai_reason) {
    return <div className="reason ai-reason"><span className="ai-badge">AI 추천 이유</span><p>{item.ai_reason}</p></div>
  }
  if (item.reason) {
    return <div className="reason rule-reason"><span className="rule-badge">조건 추천 이유</span><p>{item.reason}</p></div>
  }
  return null
}
// 예전 데이터는 '시설' 칸에 '종류 · 주소'가 함께 들어 있어, 주소는 따로 보여주고 종류만 남깁니다.
function facilityLabel(item: Candidate) {
  const address = item.regions.join(' ').trim()
  const parts = (item.facility || '').split(' · ').map(part => part.trim()).filter(part => part && part !== address)
  return parts.join(' · ')
}
function FeeBadge({ type }: { type?: string }) {
  return type === 'paid' ? <span className="fee-badge paid">유료</span> : <span className="fee-badge free">무료</span>
}
function CandidateDetails({ item }: { item: Candidate }) {
  if (item.kind === 'space') return <dl className="candidate-details space-details">
    <div className="fee-row"><dt>요금</dt><dd>{item.fee_note || (item.fee_type === 'paid' ? '요금은 매장에서 직접 확인해 주세요' : '무료')}</dd></div>
    <div><dt>시설</dt><dd>{facilityLabel(item) || '학습 공간'}</dd></div>
    {item.regions.length > 0 && <div><dt>주소</dt><dd>{item.regions.join(' ')}</dd></div>}
    <div><dt>운영시간</dt><dd>{item.operating_hours || '공식 안내에서 확인'}</dd></div>
    <div><dt>이용 절차</dt><dd>{item.usage_procedure || '공식 안내에서 확인'}</dd></div>
  </dl>
  return <dl className="candidate-details mentor-details">
    {item.intro && <div className="intro-detail"><dt>멘토 소개</dt><dd>{item.intro}</dd></div>}
    <div><dt>안내 가능 도구·수준</dt><dd>{item.tools.join(' · ')} / {item.levels.join(' · ')}</dd></div>
    {item.topics && item.topics.length > 0 && <div><dt>가르칠 수 있는 주제</dt><dd>{item.topics.join(' · ')}</dd></div>}
    <div><dt>가능 요일·시간</dt><dd>{item.times.join(' · ')}</dd></div>
    <div><dt>활동 지역</dt><dd>{item.regions.join(' · ')}</dd></div>
  </dl>
}
export default function RecommendationList({ title, items, selected, onSelect, onSkip, skipped, aiRanked, kind: kindProp }: Props) {
  const kind = kindProp ?? (items[0]?.kind === 'space' ? 'space' : 'mentor')
  const isSpace = kind === 'space'
  const paidList = isSpace && (items.some(item => item.fee_type === 'paid') || title.includes('유료'))
  const hasSelection = Boolean(selected && items.some(item => item.id === selected.id && item.kind === selected.kind))
  const effectiveDone = hasSelection || (isSpace && Boolean(skipped))
  // 서버가 정한 순서(AI 매칭 순서)를 그대로 유지하고, 선택한 후보만 맨 위로 올립니다.
  const orderedItems = items.map((item, index) => ({ item, index })).sort((a, b) => {
    const aChosen = a.item.id === selected?.id && a.item.kind === selected?.kind
    const bChosen = b.item.id === selected?.id && b.item.kind === selected?.kind
    if (aChosen !== bChosen) return aChosen ? -1 : 1
    return a.index - b.index
  }).map(entry => entry.item)
  const countLabel = isSpace ? '곳' : '명'
  return <section className={`result-section ${kind}-results`} aria-labelledby={`${title}-heading`}>
    <div className="section-head"><div><p className="eyebrow">우리동네 인근 {isSpace ? (paidList ? '유료 학습 공간' : '무료 학습 공간') : '멘토'} 후보</p><h2 id={`${title}-heading`}>{title}</h2></div><span className="count">{items.length}{countLabel}</span></div>
    {!isSpace && (aiRanked
      ? <div className="ai-panel"><span className="ai-panel-face" aria-hidden="true">✦</span><div><strong>AI가 멘토 순서를 정했어요</strong><ol><li>적어주신 <b>배우고 싶은 내용</b>을 멘토의 주제·소개글과 비교했어요.</li><li>도구·수준·기기·시간·동이 얼마나 맞는지 함께 봤어요.</li><li>카드마다 <b>AI 추천 이유</b>를 적어 두었어요.</li></ol></div></div>
      : <div className="ai-panel rule"><span className="ai-panel-face" aria-hidden="true">⚙</span><div><strong>조건으로 고른 추천이에요</strong><p>AI 연결이 늦어져서, 도구·수준·기기·시간·동이 맞는 정도로 먼저 골랐어요. 잠시 뒤 ‘조건 수정하기’로 다시 찾으면 AI 추천을 받을 수 있어요.</p></div></div>)}
    {isSpace && <p className="list-notice">{paidList ? '요금과 운영시간은 매장마다 달라요. 이용 전에 매장에 직접 확인해 주세요.' : '아래 공간은 추천 후보이며, 실제 이용 가능 여부는 공식 페이지에서 다시 확인해주세요.'}</p>}
    <div className="candidate-list">
      {!effectiveDone && (isSpace && onSkip
        ? <p className="selection-guide sticky" role="status"><span>선택해 주세요.</span><button className="outline press" onClick={onSkip}>추천 공간 선택 없이 진행 →</button></p>
        : <p className="selection-guide" role="status">선택해 주세요.</p>)}
      {isSpace && skipped && !hasSelection && <p className="selection-guide" role="status">공간 선택 없이 진행하기로 했어요. 아래에서 공간을 다시 고를 수도 있어요.</p>}
      {items.length === 0 ? <div className="empty"><strong>추천 후보가 아직 없습니다.</strong><p>검색 조건을 조금 바꾸어 다시 찾아보세요.</p></div> : orderedItems.map(item => {
        const chosen = selected?.id === item.id && selected?.kind === item.kind
        return <article className={`candidate ${item.kind} ${chosen ? 'chosen' : ''}`} key={item.id}>
          <div className="candidate-top">{item.kind === 'space' ? <span className={`space-icon ${item.fee_type === 'paid' ? 'paid' : 'free'}`} aria-hidden="true"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"><path d="M3 10l9-6 9 6v10H3z" /><path d="M9 20v-6h6v6" /></svg></span> : <Avatar name={item.name} size={48} />}<div className="candidate-name"><h3>{item.name}{item.kind === 'space' && <> <FeeBadge type={item.fee_type}/></>}</h3>{item.kind === 'mentor' ? <small>{item.tools.join(' · ')} 멘토{item.regions[0] ? ` · ${item.regions[0]}` : ''}</small> : <small>{facilityLabel(item) || '학습 공간'}</small>}{item.kind === 'space' && (item as any).nearby_label && <span className="nearby-badge">{(item as any).nearby_label}</span>}</div><MatchBadge item={item}/></div>
          <MetaChips item={item}/>
          <RecommendReason item={item}/>
          <CandidateDetails item={item}/>
          <div className="source"><span>출처 · {item.source}</span><span>기준일 · {item.source_date}</span></div>
          <div className="candidate-actions">{item.kind === 'space' && item.official_url && <a className="outline press map-link" href={item.official_url} target="_blank" rel="noreferrer">{item.fee_type === 'paid' ? '지도에서 요금·위치 확인' : '공식 안내 보기'}</a>}<button className={chosen ? 'primary press' : 'outline press'} onClick={() => onSelect(item)}>{chosen ? '✓ 선택됨' : `이 ${isSpace ? '공간' : '멘토'} 선택`}</button></div>
        </article>
      })}
    </div>
  </section>
}
