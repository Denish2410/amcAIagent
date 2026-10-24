import React, { useState } from 'react';
import { 
  ChevronDown, 
  ChevronRight, 
  Wrench, 
  Eye, 
  MapPin, 
  Building2, 
  FileCheck2, 
  Clock, 
  AlertOctagon, 
  ListFilter 
} from 'lucide-react';

const TOOL_ICONS = {
  analyze_image: Eye,
  extract_photo_location: MapPin,
  lookup_ward: MapPin,
  lookup_department: Building2,
  create_complaint: FileCheck2,
  get_complaint_status: Clock,
  escalate_complaint: AlertOctagon,
  list_my_complaints: ListFilter,
};

export default function AgentTrace({ trace = [] }) {
  const [isOpen, setIsOpen] = useState(false);

  if (!trace || trace.length === 0) return null;

  return (
    <div className="trace-accordion">
      <div 
        className="trace-accordion-summary"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
          <Wrench size={14} />
          <span>🔧 Agent Steps & Reasoning ({trace.length} tool {trace.length === 1 ? 'call' : 'calls'})</span>
        </div>
        {isOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
      </div>

      {isOpen && (
        <div className="trace-steps-body animate-fade-in">
          {trace.map((step, idx) => {
            const IconComponent = TOOL_ICONS[step.tool] || Wrench;
            return (
              <div key={idx} className="trace-step-item">
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
                  <div className="step-tool-badge">
                    <IconComponent size={12} />
                    <span>{idx + 1}. {step.tool}</span>
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                  {step.args && Object.keys(step.args).length > 0 && (
                    <div>
                      <span style={{ fontSize: '0.7rem', color: '#94a3b8', fontWeight: 600 }}>Arguments:</span>
                      <pre className="step-json-block">{JSON.stringify(step.args, null, 2)}</pre>
                    </div>
                  )}

                  {step.result && (
                    <div>
                      <span style={{ fontSize: '0.7rem', color: '#10b981', fontWeight: 600 }}>Output:</span>
                      <pre className="step-json-block" style={{ color: '#86efac' }}>
                        {JSON.stringify(step.result, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
