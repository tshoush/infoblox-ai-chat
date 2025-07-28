import React from 'react';
import './StatusIndicator.css';

interface StatusIndicatorProps {
  status: 'healthy' | 'degraded' | 'unhealthy';
  lastChecked: Date;
  className?: string;
}

const StatusIndicator: React.FC<StatusIndicatorProps> = ({ 
  status, 
  lastChecked, 
  className = '' 
}) => {
  const getStatusIcon = () => {
    switch (status) {
      case 'healthy':
        return (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5"/>
            <path d="M6 8l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        );
      case 'degraded':
        return (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M8 2l6 12H2L8 2z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M8 6v3M8 12h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
        );
      case 'unhealthy':
        return (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5"/>
            <path d="M6 6l4 4M10 6l-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
        );
      default:
        return null;
    }
  };

  const getStatusText = () => {
    switch (status) {
      case 'healthy':
        return 'System operational';
      case 'degraded':
        return 'Limited functionality';
      case 'unhealthy':
        return 'System unavailable';
      default:
        return 'Status unknown';
    }
  };

  const getStatusColor = () => {
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

  const formatLastChecked = () => {
    const now = new Date();
    const diffMs = now.getTime() - lastChecked.getTime();
    const diffSeconds = Math.floor(diffMs / 1000);
    const diffMinutes = Math.floor(diffSeconds / 60);

    if (diffSeconds < 60) {
      return 'Just now';
    } else if (diffMinutes < 60) {
      return `${diffMinutes}m ago`;
    } else {
      return lastChecked.toLocaleTimeString([], { 
        hour: '2-digit', 
        minute: '2-digit' 
      });
    }
  };

  const containerClass = `status-indicator status-indicator-${status} ${className}`.trim();

  return (
    <div 
      className={containerClass}
      role="status"
      aria-live="polite"
      aria-label={`System status: ${getStatusText()}, last checked ${formatLastChecked()}`}
    >
      <div className="status-content">
        <div 
          className="status-icon"
          style={{ color: getStatusColor() }}
          aria-hidden="true"
        >
          {getStatusIcon()}
        </div>
        
        <div className="status-details">
          <div className="status-text">
            {getStatusText()}
          </div>
          <div className="status-timestamp">
            Last checked: {formatLastChecked()}
          </div>
        </div>
      </div>
      
      <div 
        className="status-pulse"
        style={{ backgroundColor: getStatusColor() }}
        aria-hidden="true"
      />
    </div>
  );
};

export default StatusIndicator;