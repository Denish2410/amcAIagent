import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

const STATUS_COLORS = {
  FILED: '#fbbf24',
  ASSIGNED: '#60a5fa',
  IN_PROGRESS: '#f97316',
  RESOLVED: '#10b981',
};

export default function CivicMap({ complaints = [] }) {
  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const markersLayerRef = useRef(null);

  useEffect(() => {
    if (!mapContainerRef.current) return;

    if (!mapInstanceRef.current) {
      // Ahmedabad centroid
      const map = L.map(mapContainerRef.current, {
        center: [23.0225, 72.5714],
        zoom: 12,
        zoomControl: true,
      });

      // CartoDB Dark Matter / Positron or OSM tiles
      L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
        maxZoom: 19,
      }).addTo(map);

      markersLayerRef.current = L.layerGroup().addTo(map);
      mapInstanceRef.current = map;
    }

    const markersLayer = markersLayerRef.current;
    markersLayer.clearLayers();

    // Add markers for complaints that have coordinates
    const validPoints = [];
    complaints.forEach((c) => {
      if (c.lat && c.lon) {
        const color = STATUS_COLORS[c.status] || '#f97316';
        validPoints.push([c.lat, c.lon]);

        const customIcon = L.divIcon({
          className: 'custom-map-pin',
          html: `
            <div style="
              width: 28px;
              height: 28px;
              background: ${color};
              border: 3px solid #ffffff;
              border-radius: 50%;
              box-shadow: 0 0 14px ${color}, 0 4px 10px rgba(0,0,0,0.5);
              display: flex;
              align-items: center;
              justify-content: center;
              font-size: 13px;
              color: #ffffff;
            ">
              📍
            </div>
          `,
          iconSize: [28, 28],
          iconAnchor: [14, 14],
        });

        const popupContent = `
          <div style="font-family: system-ui, sans-serif; min-width: 200px; color: #1e293b; padding: 4px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <span style="font-weight: 800; font-size: 13px; color: #0f172a;">${c.tracking_id}</span>
              <span style="background: ${color}20; color: ${color}; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 700;">
                ${c.status}
              </span>
            </div>
            <div style="font-size: 12px; margin-bottom: 4px;">
              <strong>${c.issue_type?.replace('_', ' ').toUpperCase()}</strong> · ${c.ward_name} Ward
            </div>
            <div style="font-size: 11px; color: #64748b; margin-bottom: 6px;">
              Dept: ${c.dept_name || c.dept_code}
            </div>
            ${c.description ? `<div style="font-size: 11px; background: #f1f5f9; padding: 6px; border-radius: 4px; margin-bottom: 6px;">"${c.description}"</div>` : ''}
            <div style="font-size: 11px; color: #475569; display: flex; justify-content: space-between;">
              <span>Upvotes: <strong>${c.upvotes}</strong></span>
              <span>Due: ${c.expected_resolution_by || 'SLA'}</span>
            </div>
          </div>
        `;

        L.marker([c.lat, c.lon], { icon: customIcon })
          .bindPopup(popupContent)
          .addTo(markersLayer);
      }
    });

    if (validPoints.length > 0 && mapInstanceRef.current) {
      const bounds = L.latLngBounds(validPoints);
      mapInstanceRef.current.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
    }

    return () => {};
  }, [complaints]);

  return (
    <div className="map-view-layout animate-fade-in">
      <div className="map-card-container">
        <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />
        
        <div className="map-legend-overlay">
          <div className="legend-item">
            <span className="legend-dot" style={{ background: STATUS_COLORS.FILED }} />
            <span>Filed ({complaints.filter(c => c.status === 'FILED').length})</span>
          </div>
          <div className="legend-item">
            <span className="legend-dot" style={{ background: STATUS_COLORS.ASSIGNED }} />
            <span>Assigned ({complaints.filter(c => c.status === 'ASSIGNED').length})</span>
          </div>
          <div className="legend-item">
            <span className="legend-dot" style={{ background: STATUS_COLORS.IN_PROGRESS }} />
            <span>In Progress ({complaints.filter(c => c.status === 'IN_PROGRESS').length})</span>
          </div>
          <div className="legend-item">
            <span className="legend-dot" style={{ background: STATUS_COLORS.RESOLVED }} />
            <span>Resolved ({complaints.filter(c => c.status === 'RESOLVED').length})</span>
          </div>
        </div>
      </div>
    </div>
  );
}
