import React from 'react';
import { Sparkles, MapPin, AlertCircle, RefreshCw, Play, Check } from 'lucide-react';

export default function DemoLab({ samples = [], onSelectSample, onResetData, resetting }) {
  return (
    <div className="demo-lab-view animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontSize: '1.35rem', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Sparkles size={22} color="#f97316" />
            <span>Interactive Demo Scenarios</span>
          </h2>
          <p style={{ fontSize: '0.88rem', color: '#94a3b8', marginTop: '0.2rem' }}>
            Test the civic agent's end-to-end vision, geotag extraction, ward routing, and conversational slot-filling in 1-click.
          </p>
        </div>

        <button 
          className="action-btn-secondary" 
          style={{ borderColor: 'rgba(239, 68, 68, 0.4)', color: '#f87171' }}
          onClick={onResetData}
          disabled={resetting}
        >
          <RefreshCw size={14} className={resetting ? 'spin-icon' : ''} />
          <span>Reset Demo Database</span>
        </button>
      </div>

      <div className="demo-lab-grid">
        {samples.map((sample) => (
          <div key={sample.id} className="sample-preset-card">
            <div className="sample-card-media">
              <img 
                src={`/api/samples/${sample.filename}`} 
                alt={sample.title}
                onError={(e) => {
                  e.target.style.display = 'none';
                }}
              />
              <span className={`sample-gps-tag ${sample.has_gps ? 'has-gps' : 'no-gps'}`}>
                {sample.has_gps ? '📍 EXIF GPS Embedded' : '⚠️ No GPS in EXIF'}
              </span>
            </div>

            <div className="sample-card-body">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.78rem', color: '#38bdf8', fontWeight: 600 }}>
                <MapPin size={13} />
                <span>{sample.location_name}</span>
              </div>

              <h4>{sample.title}</h4>
              <p>{sample.description}</p>

              <div className="sample-card-actions">
                <button 
                  className="btn-trigger-sample"
                  onClick={() => onSelectSample(sample)}
                >
                  <Play size={14} fill="currentColor" />
                  <span>Test This Scenario</span>
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
