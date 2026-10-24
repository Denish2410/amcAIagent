import React, { useState } from 'react';
import { 
  Briefcase, 
  CheckCircle2, 
  Clock, 
  AlertTriangle, 
  Search, 
  ArrowRight, 
  ThumbsUp, 
  RefreshCw,
  Phone,
  UserCheck
} from 'lucide-react';

export default function OfficerConsole({ complaints = [], onAdvanceStatus, onRefresh, loading }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');

  const total = complaints.length;
  const inProgress = complaints.filter(c => c.status === 'IN_PROGRESS' || c.status === 'ASSIGNED').length;
  const resolved = complaints.filter(c => c.status === 'RESOLVED').length;
  const overdue = complaints.filter(c => c.overdue).length;

  const filtered = complaints.filter(c => {
    const matchesSearch = 
      c.tracking_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.ward_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.dept_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.issue_type?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.description?.toLowerCase().includes(searchTerm.toLowerCase());
    
    const matchesStatus = statusFilter === 'ALL' || c.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="officer-view-layout animate-fade-in">
      {/* Metrics Row */}
      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-info">
            <h3>Total Complaints</h3>
            <p>{total}</p>
          </div>
          <div className="metric-icon-box" style={{ background: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8' }}>
            <Briefcase size={24} />
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-info">
            <h3>Active / Assigned</h3>
            <p>{inProgress}</p>
          </div>
          <div className="metric-icon-box" style={{ background: 'rgba(249, 115, 22, 0.15)', color: '#f97316' }}>
            <Clock size={24} />
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-info">
            <h3>Resolved</h3>
            <p style={{ color: '#10b981' }}>{resolved}</p>
          </div>
          <div className="metric-icon-box" style={{ background: 'rgba(16, 185, 129, 0.15)', color: '#10b981' }}>
            <CheckCircle2 size={24} />
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-info">
            <h3>Overdue Tickets</h3>
            <p style={{ color: '#ef4444' }}>{overdue}</p>
          </div>
          <div className="metric-icon-box" style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#ef4444' }}>
            <AlertTriangle size={24} />
          </div>
        </div>
      </div>

      {/* Complaints Board / Table */}
      <div className="complaints-table-card">
        <div className="table-toolbar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem', flexWrap: 'wrap' }}>
            <div style={{ position: 'relative' }}>
              <input 
                type="text" 
                placeholder="Search ticket, ward, issue..." 
                className="table-search-input"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>

            <select 
              className="table-search-input"
              style={{ minWidth: '140px' }}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="ALL">All Statuses</option>
              <option value="FILED">Filed</option>
              <option value="ASSIGNED">Assigned</option>
              <option value="IN_PROGRESS">In Progress</option>
              <option value="RESOLVED">Resolved</option>
            </select>
          </div>

          <div className="table-actions">
            <button 
              className="action-btn-secondary"
              onClick={onRefresh}
              disabled={loading}
            >
              <RefreshCw size={14} className={loading ? 'spin-icon' : ''} />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        <div className="complaints-table-wrapper">
          <table className="civic-table">
            <thead>
              <tr>
                <th>Ticket ID</th>
                <th>Issue & Ward</th>
                <th>Department & Officer</th>
                <th>Citizen Support</th>
                <th>Timeline Stage</th>
                <th>Due / SLA</th>
                <th>Officer Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan="7" style={{ textAlign: 'center', padding: '2.5rem', color: '#64748b' }}>
                    No complaints found matching criteria.
                  </td>
                </tr>
              ) : (
                filtered.map((c) => (
                  <tr key={c.tracking_id}>
                    <td>
                      <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#38bdf8' }}>
                        {c.tracking_id}
                      </div>
                      <div style={{ fontSize: '0.72rem', color: '#64748b' }}>
                        {new Date(c.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </div>
                    </td>

                    <td>
                      <div style={{ fontWeight: 600, textTransform: 'capitalize' }}>
                        {c.issue_type?.replace('_', ' ')}
                      </div>
                      <div style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
                        {c.ward_name} Ward ({c.zone_name})
                      </div>
                    </td>

                    <td>
                      <div style={{ fontWeight: 500, fontSize: '0.82rem' }}>
                        {c.dept_name}
                      </div>
                      {c.officer_designation && (
                        <div style={{ fontSize: '0.75rem', color: '#64748b', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <UserCheck size={12} />
                          <span>{c.officer_designation}</span>
                        </div>
                      )}
                    </td>

                    <td>
                      <div style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', background: 'rgba(255, 255, 255, 0.05)', padding: '2px 8px', borderRadius: '4px', fontSize: '0.8rem', fontWeight: 600 }}>
                        <ThumbsUp size={12} color="#f97316" />
                        <span>{c.upvotes} {c.upvotes === 1 ? 'citizen' : 'citizens'}</span>
                      </div>
                    </td>

                    <td>
                      <span className={`badge-status ${c.status}`}>
                        {c.status.replace('_', ' ')}
                      </span>
                    </td>

                    <td>
                      <div style={{ fontSize: '0.82rem', color: c.overdue ? '#ef4444' : '#94a3b8', fontWeight: c.overdue ? 700 : 500 }}>
                        {c.expected_resolution_by || 'Standard SLA'}
                        {c.overdue && <span style={{ marginLeft: '4px' }}>⚠️ Overdue</span>}
                      </div>
                    </td>

                    <td>
                      {c.status !== 'RESOLVED' ? (
                        <button 
                          className="btn-advance-status"
                          onClick={() => onAdvanceStatus(c.tracking_id)}
                          title="Advance to next workflow stage"
                        >
                          <span>Next</span>
                          <ArrowRight size={13} />
                        </button>
                      ) : (
                        <span style={{ fontSize: '0.75rem', color: '#10b981', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                          <CheckCircle2 size={13} />
                          <span>Completed</span>
                        </span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
