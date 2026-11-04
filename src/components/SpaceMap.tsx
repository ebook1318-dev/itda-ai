import { useMemo } from 'react'
import { CircleMarker, MapContainer, Popup, TileLayer } from 'react-leaflet'
import { Candidate } from '../data'

type Props = { items: Candidate[]; selected?: Candidate | null; onSelect: (candidate: Candidate) => void }

export default function SpaceMap({ items, selected, onSelect }: Props) {
  const points = items.filter(item => typeof item.lat === 'number' && typeof item.lng === 'number')
  const groups = useMemo(() => Object.values(points.reduce<Record<string, Candidate[]>>((acc, item) => {
    const key = `${item.lat!.toFixed(4)}:${item.lng!.toFixed(4)}`
    ;(acc[key] ||= []).push(item)
    return acc
  }, {})), [points])
  const center: [number, number] = points.length ? [points[0].lat!, points[0].lng!] : [36.8151, 127.1139]
  if (!points.length) return null
  return <div className="space-map-wrap">
    <MapContainer center={center} zoom={12} scrollWheelZoom={false} className="space-map-view">
      <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {groups.map(group => {
        const first = group[0]
        const chosen = group.some(item => selected?.id === item.id && selected?.kind === item.kind)
        return <CircleMarker key={`${first.lat}:${first.lng}`} center={[first.lat!, first.lng!]} radius={group.length > 1 ? 16 : 11} pathOptions={{ color: chosen ? '#0B50D0' : '#256EF4', fillColor: chosen ? '#0B50D0' : '#256EF4', fillOpacity: 0.85, weight: 2 }}>
          <Popup>
            {group.map(item => <button key={item.id} className="map-popup-item press" onClick={() => onSelect(item)}>
              <strong>{item.name}</strong>
              <span>{item.neighborhoods.join(', ') || '위치 정보 없음'}</span>
            </button>)}
          </Popup>
        </CircleMarker>
      })}
    </MapContainer>
    <p className="map-note">핀 위치는 건물 정확 주소가 아니라 동 단위 대략적인 위치예요. 정확한 위치는 공식 안내에서 확인해 주세요.</p>
  </div>
}
