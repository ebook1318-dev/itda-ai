import { Candidate, MatchTier } from '../data'
type Props = {
  title: string
  items: Candidate[]
  selected?: Candidate | null
  onSelect: (candidate: Candidate) => void
  onSkip?: () => void
  skipped?: boolean
}
function tierFromPercent(percent: number): MatchTier {
  return percent >= 70 ? 'match' : percent >= 45 ? 'partial' : 'miss'
}
function MatchBadge({ percent }: { percent: number | null }) {
  if (percent === null) return null
  const tier = tierFromPercent(percent)
  return <span className={`match-badge tier-${tier}`}>일치도 {percent}%</span>
}
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
    const tier = row.key === 'keyword' && field.tier === 'miss' ? 'neutral' : field.tier
    return <span className={`meta-item ${tier}`} key={row.key}><span className="dot"></span>{row.label} · {field.label}</span>
  })}</div>
}
function CandidateDetails({ item }: { item: Candidate }) {
  if (item.kind === 'space') return <dl className="candidate-details space-details">
    <div><dt>시설</dt><dd>{item.facility || '학습 공간'}</dd></div>
    <div><dt>운영시간</dt><dd>{item.operating_hours || '공식 안내에서 확인'}</dd></div>
    <div><dt>이용 절차</dt><dd>{item.usage_procedure || '공식 안내에서 확인'}</dd></div>
  </dl>
  return <dl className="candidate-details mentor-details">
    <div><dt>안내 가능 도구·수준</dt><dd>{item.tools.join(' · ')} / {item.levels.join(' · ')}</dd></div>
    {item.topics && item.topics.length > 0 && <div><dt>가르칠 수 있는 주제</dt><dd>{item.topics.join(' · ')}</dd></div>}
    <div><dt>가능 요일·시간</dt><dd>{item.times.join(' · ')}</dd></div>
    <div><dt>활동 지역</dt><dd>{item.regions.join(' · ')}</dd></div>
  </dl>
}
export default function RecommendationList({ title, items, selected, onSelect, onSkip, skipped }: Props) {
  const kind = items[0]?.kind === 'space' ? 'space' : 'mentor'
  const isSpace = kind === 'space'
  const hasSelection = Boolean(selected && items.some(item => item.id === selected.id && item.kind === selected.kind))
  const effectiveDone = hasSelection || (isSpace && Boolean(skipped))
  const orderedItems = [...items].sort((a, b) => {
    const aChosen = a.id === selected?.id && a.kind === selected?.kind
    const bChosen = b.id === selected?.id && b.kind === selected?.kind
    if (aChosen !== bChosen) return aChosen ? -1 : 1
    return b.score - a.score
  })
  const countLabel = isSpace ? '곳' : '명'
  return <section className={`result-section ${kind}-results`} aria-labelledby={`${title}-heading`}>
    <div className="section-head"><div><p className="eyebrow">우리동네 인근 {isSpace ? '공공 학습 공간' : '멘토'} 후보</p><h2 id={`${title}-heading`}>{title}</h2></div><span className="count">{items.length}{countLabel}</span></div>
    {isSpace && <p className="list-notice">아래 공간은 추천 후보이며, 실제 이용 가능 여부는 공식 페이지에서 다시 확인해주세요.</p>}
    <div className="candidate-list">
      {!effectiveDone && (isSpace && onSkip
        ? <p className="selection-guide sticky" role="status"><span>선택해 주세요.</span><button className="outline press" onClick={onSkip}>추천 공간 선택 없이 진행 →</button></p>
        : <p className="selection-guide" role="status">선택해 주세요.</p>)}
      {isSpace && skipped && !hasSelection && <p className="selection-guide" role="status">공간 선택 없이 진행하기로 했어요. 아래에서 공간을 다시 고를 수도 있어요.</p>}
      {items.length === 0 ? <div className="empty"><strong>추천 후보가 아직 없습니다.</strong><p>검색 조건을 조금 바꾸어 다시 찾아보세요.</p></div> : orderedItems.map(item => {
        const chosen = selected?.id === item.id && selected?.kind === item.kind
        return <article className={`candidate ${item.kind} ${chosen ? 'chosen' : ''}`} key={item.id}>
          <div className="candidate-top"><h3>{item.name}</h3><MatchBadge percent={item.match_percent}/></div>
          <MetaChips item={item}/>
          <CandidateDetails item={item}/>
          <div className="source"><span>출처 · {item.source}</span><span>기준일 · {item.source_date}</span></div>
          <div className="candidate-actions"><button className={chosen ? 'primary press' : 'outline press'} onClick={() => onSelect(item)}>{chosen ? '선택됨' : `${isSpace ? '공간' : '멘토'} 선택`}</button></div>
        </article>
      })}
    </div>
  </section>
}
