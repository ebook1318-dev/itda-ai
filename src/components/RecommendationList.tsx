import { Candidate } from '../data'

type Props = {
  title: string
  items: Candidate[]
  selected?: Candidate | null
  onSelect: (candidate: Candidate) => void
}

function CandidateDetails({ item }: { item: Candidate }) {
  if (item.kind === 'space') return <dl className="candidate-details space-details">
    <div><dt>시설</dt><dd>{item.facility || '학습 공간'}</dd></div>
    <div><dt>운영시간</dt><dd>{item.operating_hours || '공식 안내에서 확인'}</dd></div>
    <div><dt>이용 절차</dt><dd>{item.usage_procedure || '공식 안내에서 확인'}</dd></div>
    <div><dt>도보 거리</dt><dd>{item.distance}</dd></div>
  </dl>
  return <dl className="candidate-details mentor-details">
    <div><dt>안내 가능 도구·수준</dt><dd>{item.tools.join(' · ')} / {item.levels.join(' · ')}</dd></div>
    <div><dt>가능 요일·시간</dt><dd>{item.times.join(' · ')}</dd></div>
    <div><dt>활동 지역</dt><dd>{item.regions.join(' · ')}</dd></div>
  </dl>
}

export default function RecommendationList({ title, items, selected, onSelect }: Props) {
  const kind = items[0]?.kind === 'space' ? 'space' : 'mentor'
  const isSpace = kind === 'space'
  return <section className={`result-section ${kind}-results`} aria-labelledby={`${title}-heading`}>
    <div className="section-head"><div><p className="eyebrow">불당동 인근 {isSpace ? '공공 학습 공간' : '멘토'} 후보</p><h2 id={`${title}-heading`}>{title}</h2></div><span className="count">{items.length}곳</span></div>
    {isSpace && <p className="list-notice">아래 공간은 추천 후보이며, 실제 이용 가능 여부는 공식 페이지에서 다시 확인해주세요.</p>}
    {items.length === 0 ? <div className="empty"><strong>딱 맞는 후보를 찾지 못했습니다.</strong><p>조건을 조금 바꾸어 다시 찾아보세요.</p></div> : <div className="candidate-list">{items.map(item => {
      const chosen = selected?.id === item.id
      return <article className={`candidate ${item.kind} ${chosen ? 'chosen' : ''}`} key={item.id}>
        <div className="candidate-top"><h3>{item.name}</h3></div>
        <CandidateDetails item={item}/>
        <div className="source"><span>출처: {item.source}</span><span>확인일: {item.source_date}</span></div>
        <div className="candidate-actions"><button className={chosen ? 'primary press' : 'outline press'} onClick={() => onSelect(item)}>{chosen ? '선택됨' : `${isSpace ? '공간' : '멘토'} 선택`}</button></div>
      </article>
    })}</div>}
  </section>
}
