import React from 'react';
import { SystemStatus } from './ChatInterface';
import './Header.css';

interface HeaderProps {
  systemStatus: SystemStatus;
  onClearChat: () => void;
  sessionId: string;
}

const Header: React.FC<HeaderProps> = ({ systemStatus, onClearChat, sessionId }) => {
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'var(--success-green)';
      case 'degraded':
        return 'var(--warning-amber)';
      case 'unhealthy':
        return 'var(--error-red)';
      default:
        return 'var(--text-secondary)';
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'All systems operational';
      case 'degraded':
        return 'Some services degraded';
      case 'unhealthy':
        return 'System unavailable';
      default:
        return 'Status unknown';
    }
  };

  return (
    <header className="chat-header" role="banner">
      <div className="header-content">
        <div className="header-left">
          <div className="logo-section">
            <div className="logo-icon">
              <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="4" y="4" width="24" height="24" rx="4" fill="var(--marriott-gold)" />
                <path d="M12 10h8v2h-8v-2zM12 14h8v2h-8v-2zM12 18h6v2h-6v-2z" fill="var(--marriott-red)" />
                <circle cx="9" cy="11" r="1" fill="var(--marriott-red)" />
                <circle cx="9" cy="15" r="1" fill="var(--marriott-red)" />
                <circle cx="9" cy="19" r="1" fill="var(--marriott-red)" />
              </svg>
            </div>
            <div className="logo-text">
              <h1 className="app-title">Infoblox AI Chat</h1>
              <p className="app-subtitle">Network Infrastructure Assistant</p>
            </div>
          </div>
        </div>

        <div className="header-center">
          <div className="system-status" role="status" aria-live="polite">
            <div 
              className="status-indicator"
              style={{ backgroundColor: getStatusColor(systemStatus.status) }}
              aria-label={`System status: ${systemStatus.status}`}
            />
            <div className="status-details">
              <span className="status-text">{getStatusText(systemStatus.status)}</span>
              <div className="status-services">
                <span 
                  className={`service-status ${systemStatus.infobloxConnected ? 'connected' : 'disconnected'}`}
                  title={`Infoblox: ${systemStatus.infobloxConnected ? 'Connected' : 'Disconnected'}`}
                >
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <rect x="1" y="1" width="10" height="10" rx="2" stroke="currentColor" strokeWidth="1.5"/>
                    <path d="M3 3h6M3 6h4M3 9h5" stroke="currentColor" strokeWidth="1" strokeLinecap="round"/>
                  </svg>
                  Infoblox
                </span>
                <span 
                  className={`service-status ${systemStatus.llmConnected ? 'connected' : 'disconnected'}`}
                  title={`AI Service: ${systemStatus.llmConnected ? 'Connected' : 'Disconnected'}`}
                >
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.5"/>
                    <path d="M4 6l1.5 1.5L8 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  AI
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="header-right">
          <div className="session-info">
            <span className="session-label">Session:</span>
            <code className="session-id" title={`Session ID: ${sessionId}`}>
              {sessionId.slice(0, 8)}...
            </code>
          </div>
          
          <div className="header-actions">
            <button
              className="button button-outline button-sm"
              onClick={onClearChat}
              title="Clear chat history"
              aria-label="Clear chat history"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M3 4h10M5 4V3a1 1 0 011-1h4a1 1 0 011 1v1M6 7v4M10 7v4M4 4v9a1 1 0 001 1h6a1 1 0 001-1V4" 
                      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Clear
            </button>
            
            <button
              className="button button-outline button-sm"
              title="System information"
              aria-label="View system information"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5"/>
                <path d="M8 6v4M8 4h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
              Info
            </button>
          </div>
        </div>
      </div>

      <div className="header-divider" />
    </header>
  );
};

export default Header;