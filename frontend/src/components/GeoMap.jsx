import React, { useEffect, useRef } from 'react'
import { MapContainer, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'

const SEVERITY_COLORS = { critical: '#ff4757', problematic: '#ffb700' }

function severityColor(severity) {
  return SEVERITY_COLORS[severity] || '#00ff87'
}

function MapPins({ decisions }) {
  const map = useMap()
  const layerRef = useRef(null)

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current)
    }
    const group = L.layerGroup()
    const pins = (decisions || []).filter(d => d.lat && d.lon)

    pins.forEach(d => {
      const color = severityColor(d.severity)
      L.circleMarker([d.lat, d.lon], {
        radius: 3, fillColor: color, fillOpacity: 0.8,
        stroke: false, interactive: true
      }).bindTooltip(
        `<span style="font-family:monospace">${d.ip}</span><br/>${d.country || ''} · ${d.reason || ''}`,
        { direction: 'top' }
      ).addTo(group)
    })

    group.addTo(map)
    layerRef.current = group

    return () => {
      if (layerRef.current) map.removeLayer(layerRef.current)
    }
  }, [decisions, map])

  return null
}

export default function GeoMap({ decisions }) {
  return (
    <div className="map-container">
      <MapContainer center={[20, 0]} zoom={2} style={{ height: '100%', width: '100%' }}
        scrollWheelZoom={true} attributionControl={true}>
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
          attribution="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"
        />
        <MapPins decisions={decisions} />
      </MapContainer>
    </div>
  )
}
