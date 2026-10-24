import React, { useState, useEffect, useRef } from 'react';
import { 
  MessageSquare, 
  Map, 
  ShieldAlert, 
  Sparkles, 
  Camera, 
  Send, 
  Paperclip, 
  X, 
  Cpu, 
  FastForward, 
  User, 
  Clock, 
  FileText,
  AlertCircle
} from 'lucide-react';
import AgentTrace from './components/AgentTrace';
import CivicMap from './components/CivicMap';
import OfficerConsole from './components/OfficerConsole';
import DemoLab from './components/DemoLab';
import './App.css';

export default function App() {
  const [activeTab, setActiveTab] = useState('chat');
  const [userId, setUserId] = useState('9876543210');
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Namaste! I am **AMC Sahayak**, your AI civic complaint agent for Ahmedabad Municipal Corporation.\n\nSnap a photo of any pothole, garbage dump, broken streetlight, or water logging, or describe the problem with an area name. I will classify it, determine your AMC ward and department, and file your ticket with live tracking!\n\nYou can also ask **"what\'s the status?"** anytime.',
      trace: []
    }
  ]);
  const [inputText, setInputText] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [filePreview, setFilePreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [complaints, setComplaints] = useState([]);
  const [samples, setSamples] = useState([]);
  const [config, setConfig] = useState({
    offline_mode: false,
    has_gemini_key: true,
    gemini_model: 'gemini-flash-latest',
    fast_forward: true
  });
  const [resetting, setResetting] = useState(false);

  const fileInputRef = useRef(null);
  const messagesEndRef = useRef(null);

  // Auto-scroll chat to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  // Load config, complaints, and samples
  const fetchConfig = async () => {
    try {
      const res = await fetch('/api/config');
      if (res.ok) setConfig(await res.json());
    } catch (e) {
      console.error('Failed to fetch config', e);
    }
  };

  const fetchComplaints = async () => {
    try {
      const res = await fetch('/api/complaints');
      if (res.ok) {
        const data = await res.json();
        setComplaints(data.complaints || []);
      }
    } catch (e) {
      console.error('Failed to fetch complaints', e);
    }
  };

  const fetchSamples = async () => {
    try {
      const res = await fetch('/api/samples');
      if (res.ok) {
        const data = await res.json();
        setSamples(data.samples || []);
      }
    } catch (e) {
      console.error('Failed to fetch samples', e);
    }
  };

  useEffect(() => {
    fetchConfig();
    fetchComplaints();
    fetchSamples();

    // Poll complaints every 8 seconds for fast-forward stage updates
    const interval = setInterval(fetchComplaints, 8000);
    return () => clearInterval(interval);
  }, []);

  // Handle file selection
  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setFilePreview(URL.createObjectURL(file));
    }
  };

  const removeSelectedFile = () => {
    setSelectedFile(null);
    if (filePreview) {
      URL.revokeObjectURL(filePreview);
      setFilePreview(null);
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Submit chat message
  const handleSendMessage = async (textToSend = inputText, fileToSend = selectedFile) => {
    if (!textToSend.trim() && !fileToSend) return;

    const currentText = textToSend;
    const currentPreview = filePreview;

    // Add user message to UI immediately
    const userMsg = {
      role: 'user',
      content: currentText,
      image: currentPreview
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText('');
    removeSelectedFile();
    setLoading(true);

    try {
      const formData = new FormData();
      formData.append('text', currentText);
      formData.append('user_id', userId);
      if (fileToSend) {
        formData.append('file', fileToSend);
      }

      const res = await fetch('/api/chat', {
        method: 'POST',
        body: formData
      });

      if (!res.ok) throw new Error('API server returned error');
      const data = await res.json();

      let assistantText = data.reply;
      if (data.warning) {
        assistantText = `_⚠️ ${data.warning}_\n\n${assistantText}`;
      }

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: assistantText,
          trace: data.trace || [],
          image_id: data.image_id
        }
      ]);

      // Refresh complaints list
      fetchComplaints();
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Sorry, I encountered an issue connecting to the civic backend. Please verify your connection or try again.',
          trace: []
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  // Advance complaint stage
  const handleAdvanceStatus = async (trackingId) => {
    try {
      const res = await fetch(`/api/complaints/${trackingId}/advance`, {
        method: 'POST'
      });
      if (res.ok) {
        await fetchComplaints();
      }
    } catch (e) {
      console.error('Failed to advance complaint', e);
    }
  };

  // Reset database
  const handleResetData = async () => {
    if (!window.confirm('Reset all demo complaints and revert database to seed data?')) return;
    setResetting(true);
    try {
      await fetch('/api/reset', { method: 'POST' });
      await fetchComplaints();
      setMessages([
        {
          role: 'assistant',
          content: 'Demo database has been successfully reset! Ready for a fresh demo run.',
          trace: []
        }
      ]);
    } catch (e) {
      console.error('Failed to reset', e);
    } finally {
      setResetting(false);
    }
  };

  // Toggle offline mode
  const toggleOfflineMode = async () => {
    const nextVal = !config.offline_mode;
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ offline_mode: nextVal })
      });
      if (res.ok) {
        setConfig(await res.json());
      }
    } catch (e) {
      console.error('Failed to update config', e);
    }
  };

  // Toggle fast forward
  const toggleFastForward = async () => {
    const nextVal = !config.fast_forward;
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fast_forward: nextVal })
      });
      if (res.ok) {
        setConfig(await res.json());
      }
    } catch (e) {
      console.error('Failed to update config', e);
    }
  };

  // Select demo sample from DemoLab
  const handleSelectSample = async (sample) => {
    try {
      const imgRes = await fetch(`/api/samples/${sample.filename}`);
      const blob = await imgRes.blob();
      const file = new File([blob], sample.filename, { type: 'image/jpeg' });
      
      setSelectedFile(file);
      setFilePreview(URL.createObjectURL(file));
      setInputText(sample.suggested_prompt);
      setActiveTab('chat');
    } catch (e) {
      console.error('Failed to load sample image', e);
    }
  };

  return (
    <div className="app-container">
      {/* Top Navigation Bar */}
      <header className="app-header">
        <div className="header-content">
          <div className="brand-section">
            <div className="brand-logo-badge">🛠️</div>
            <div className="brand-title-wrap">
              <h1>
                <span>AMC Sahayak</span>
                <span className="gujarati">અમદાવાદ મ્યુનિસિપલ કોર્પોરેશન</span>
              </h1>
              <p>Civic Complaint & Resolution Agent · AI Function Calling</p>
            </div>
          </div>

          <nav className="header-nav">
            <button 
              className={`nav-tab-btn ${activeTab === 'chat' ? 'active' : ''}`}
              onClick={() => setActiveTab('chat')}
            >
              <MessageSquare size={16} />
              <span>Civic Agent</span>
            </button>

            <button 
              className={`nav-tab-btn ${activeTab === 'map' ? 'active' : ''}`}
              onClick={() => setActiveTab('map')}
            >
              <Map size={16} />
              <span>Civic Map</span>
            </button>

            <button 
              className={`nav-tab-btn ${activeTab === 'officer' ? 'active' : ''}`}
              onClick={() => setActiveTab('officer')}
            >
              <ShieldAlert size={16} />
              <span>Officer Console</span>
            </button>

            <button 
              className={`nav-tab-btn ${activeTab === 'demolab' ? 'active' : ''}`}
              onClick={() => setActiveTab('demolab')}
            >
              <Sparkles size={16} />
              <span>Demo Lab</span>
            </button>
          </nav>

          <div className="header-actions">
            {/* Offline / Gemini Status Indicator */}
            <div 
              className={`status-indicator ${config.offline_mode ? 'offline' : 'gemini'}`}
              title="Click to toggle offline rule-based agent vs Gemini API"
              onClick={toggleOfflineMode}
              style={{ cursor: 'pointer' }}
            >
              <span className="dot" />
              <span>{config.offline_mode ? 'Offline Engine' : `Gemini (${config.gemini_model.replace('gemini-', '')})`}</span>
            </div>

            {/* Fast-forward toggle */}
            <button 
              className="action-btn-secondary"
              onClick={toggleFastForward}
              title="Demo clock fast-forwards ticket stages every 1-3 mins"
              style={{ fontSize: '0.75rem', padding: '0.3rem 0.65rem' }}
            >
              <FastForward size={14} color={config.fast_forward ? '#f97316' : '#94a3b8'} />
              <span>{config.fast_forward ? 'Fast-Forward ON' : 'Realtime'}</span>
            </button>

            {/* User ID */}
            <div className="user-id-badge" title="Citizen Phone Number / ID for tracking">
              <User size={13} />
              <input 
                type="text" 
                value={userId} 
                onChange={(e) => setUserId(e.target.value)}
              />
            </div>
          </div>
        </div>
      </header>

      {/* Main Tab Views */}
      <main className="main-wrapper">
        {activeTab === 'chat' && (
          <div className="chat-layout animate-fade-in">
            {/* Chat Stream Card */}
            <div className="chat-card">
              <div className="chat-card-header">
                <div className="chat-header-title">
                  <MessageSquare size={17} color="#f97316" />
                  <span>Report Civic Grievance · Chat with AMC Sahayak</span>
                </div>
                <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                  Citizen: <strong>{userId}</strong>
                </div>
              </div>

              <div className="chat-messages-container">
                {messages.map((m, idx) => (
                  <div key={idx} className={`message-bubble-row ${m.role}`}>
                    <div className={`avatar-icon ${m.role}`}>
                      {m.role === 'user' ? '👤' : '🛠️'}
                    </div>

                    <div className="bubble-content">
                      {m.image && (
                        <div className="bubble-photo-preview">
                          <img src={m.image} alt="User attachment" />
                        </div>
                      )}

                      {m.content && (
                        <div className="bubble-text-box">
                          {m.content}
                        </div>
                      )}

                      {m.trace && m.trace.length > 0 && (
                        <AgentTrace trace={m.trace} />
                      )}
                    </div>
                  </div>
                ))}

                {loading && (
                  <div className="message-bubble-row assistant">
                    <div className="avatar-icon assistant">🛠️</div>
                    <div className="bubble-content">
                      <div className="bubble-text-box" style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                        <span className="spin-icon" style={{ display: 'inline-block' }}>⚙️</span>
                        <span>Analyzing civic issue, GPS EXIF & routing to AMC ward department...</span>
                      </div>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Chat Footer */}
              <div className="chat-footer">
                {/* Quick Suggestion Chips */}
                <div className="quick-prompts-row">
                  <button 
                    className="quick-chip"
                    onClick={() => handleSendMessage("What's the status?")}
                  >
                    🔍 What's the status?
                  </button>
                  <button 
                    className="quick-chip"
                    onClick={() => handleSendMessage("મારી ફરિયાદનું શું થયું?")}
                  >
                    🇮🇳 મારી ફરિયાદનું શું થયું?
                  </button>
                  <button 
                    className="quick-chip"
                    onClick={() => handleSendMessage("Pothole near Vastrapur lake")}
                  >
                    🕳️ Pothole near Vastrapur
                  </button>
                  <button 
                    className="quick-chip"
                    onClick={() => handleSendMessage("Broken streetlight near Iscon")}
                  >
                    💡 Streetlight near Iscon
                  </button>
                  <button 
                    className="quick-chip"
                    onClick={() => handleSendMessage("Garbage pile near Kankaria lake")}
                  >
                    🗑️ Garbage near Kankaria
                  </button>
                  <button 
                    className="quick-chip"
                    onClick={() => handleSendMessage("Please escalate my complaint")}
                  >
                    🚨 Escalate complaint
                  </button>
                </div>

                {/* File Attachment Bar */}
                {filePreview && (
                  <div className="file-preview-bar animate-fade-in">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <Camera size={15} />
                      <span>{selectedFile?.name || 'Photo attached'}</span>
                    </div>
                    <button 
                      onClick={removeSelectedFile}
                      style={{ background: 'transparent', color: '#ef4444', padding: '2px' }}
                    >
                      <X size={15} />
                    </button>
                  </div>
                )}

                {/* Input Bar */}
                <div className="chat-input-controls">
                  <input 
                    type="file" 
                    accept="image/*"
                    ref={fileInputRef}
                    style={{ display: 'none' }}
                    onChange={handleFileChange}
                  />

                  <button 
                    className="photo-attach-btn"
                    title="Attach Photo (JPG, PNG with optional EXIF GPS)"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <Camera size={19} />
                  </button>

                  <input 
                    type="text" 
                    placeholder="Type a message or describe the location (e.g., 'near Kankaria lake')..." 
                    className="chat-input-field"
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleSendMessage();
                      }
                    }}
                  />

                  <button 
                    className="chat-send-btn"
                    disabled={loading || (!inputText.trim() && !selectedFile)}
                    onClick={() => handleSendMessage()}
                  >
                    <Send size={18} />
                  </button>
                </div>
              </div>
            </div>

            {/* Sidebar Overview Cards */}
            <div className="chat-sidebar-cards">
              <div className="sidebar-panel">
                <div className="panel-header">
                  <Clock size={16} color="#f97316" />
                  <span>My Recent Complaints</span>
                </div>
                {complaints.filter(c => c.user_id === userId).length === 0 ? (
                  <p style={{ fontSize: '0.82rem', color: '#64748b' }}>
                    No complaints filed under this mobile number yet. Send a photo to file your first ticket!
                  </p>
                ) : (
                  complaints
                    .filter(c => c.user_id === userId)
                    .slice(0, 4)
                    .map((c) => (
                      <div key={c.tracking_id} className="recent-complaint-pill">
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontWeight: 700, color: '#38bdf8' }}>{c.tracking_id}</span>
                          <span className={`badge-status ${c.status}`} style={{ fontSize: '0.68rem', padding: '1px 6px' }}>
                            {c.status}
                          </span>
                        </div>
                        <div style={{ color: '#cbd5e1', fontSize: '0.78rem', textTransform: 'capitalize' }}>
                          {c.issue_type.replace('_', ' ')} · {c.ward_name}
                        </div>
                      </div>
                    ))
                )}
              </div>

              <div className="sidebar-panel">
                <div className="panel-header">
                  <Sparkles size={16} color="#06b6d4" />
                  <span>Demo Highlights</span>
                </div>
                <ul style={{ fontSize: '0.8rem', color: '#94a3b8', paddingLeft: '1.2rem', lineHeight: 1.6 }}>
                  <li><strong>EXIF GPS</strong>: Automatically extracts coordinates and maps to the exact AMC ward centroid.</li>
                  <li><strong>Smart Slot Filling</strong>: Missing GPS? Agent asks for landmark & matches aliases.</li>
                  <li><strong>Deduplication</strong>: Merges reports within 150m and raises ticket priority.</li>
                  <li><strong>Gujarati & Multilingual</strong>: Speaks Gujarati, Hindi, and English.</li>
                </ul>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'map' && (
          <CivicMap complaints={complaints} />
        )}

        {activeTab === 'officer' && (
          <OfficerConsole 
            complaints={complaints}
            onAdvanceStatus={handleAdvanceStatus}
            onRefresh={fetchComplaints}
            loading={loading}
          />
        )}

        {activeTab === 'demolab' && (
          <DemoLab 
            samples={samples}
            onSelectSample={handleSelectSample}
            onResetData={handleResetData}
            resetting={resetting}
          />
        )}
      </main>
    </div>
  );
}
