import { FormValues } from '../data'
type Props = { values: FormValues & { neighborhood?: string }; onEdit: () => void }
function neighborhoodLabel(list: string[]) {
  if (list.length <= 3) return list.map(item => <span key={`neighborhood-${item}`}>동 · {item}</span>)
  return [<span key="neighborhood-summary">동 · {list[0]} 외 {list.length - 1}곳</span>]
}
export default function ConditionSummary({ values, onEdit }: Props) {
  return <section className="summary"><div><p className="eyebrow">선택한 조건 · 우리동네 기준</p><h2>가까운 배움을 찾아봤어요</h2>{values.keyword && <p className="summary-keyword">"{values.keyword}"</p>}<div className="chips">{values.tool && <span>도구 · {values.tool}</span>}{values.level && <span>수준 · {values.level}</span>}{values.devices?.map(item => <span key={`device-${item}`}>기기 · {item}</span>)}{values.time_slots?.map(item => <span key={`time-${item}`}>시간 · {item}</span>)}{values.neighborhoods ? neighborhoodLabel(values.neighborhoods) : null}</div></div><button className="outline press" onClick={onEdit}>조건 수정하기</button></section>
}
