import React from 'react';
import { ChatMessage } from './ChatInterface';
import LoadingSpinner from './LoadingSpinner';
import './MessageList.css';

interface MessageListProps {
  messages: ChatMessage[];
  isLoading: boolean;
}

const MessageList: React.FC<MessageListProps> = ({ messages, isLoading }) => {
  const formatTimestamp = (timestamp: Date) => {
    return timestamp.toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit' 
    });
  };

  const formatNetworkData = (content: string) => {
    // Check if content looks like structured data (JSON, table-like)
    try {
      const parsed = JSON.parse(content);
      if (Array.isArray(parsed) && parsed.length > 0) {
        return formatAsTable(parsed);
      }
    } catch {
      // Not JSON, continue with regular formatting
    }

    // Format IP addresses, networks, and other network concepts
    const networkFormatted = content
      .replace(/(\b(?:\d{1,3}\.){3}\d{1,3}\b)/g, '<code class="ip-address">$1</code>')
      .replace(/(\b(?:\d{1,3}\.){3}\d{1,3}\/\d{1,2}\b)/g, '<code class="network">$1</code>')
      .replace(/(\b[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b)/g, '<code class="hostname">$1</code>');

    return { __html: networkFormatted };
  };

  const formatAsTable = (data: any[]) => {
    if (!data || data.length === 0) return null;

    const headers = Object.keys(data[0]);
    
    return (
      <div className="data-table-container">
        <table className="data-table">
          <thead>
            <tr>
              {headers.map(header => (
                <th key={header}>{header.replace(/_/g, ' ').toUpperCase()}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, index) => (
              <tr key={index}>
                {headers.map(header => (
                  <td key={header}>
                    <code className="table-value">
                      {typeof row[header] === 'object' 
                        ? JSON.stringify(row[header]) 
                        : String(row[header] || '')
                      }
                    </code>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  const renderMessageContent = (message: ChatMessage) => {
    if (message.messageType === 'api_call' && message.metadata?.proposedCalls?.length) {
      return (
        <div className="api-call-preview">
          <div className="message-text">
            <div dangerouslySetInnerHTML={formatNetworkData(message.content)} />
          </div>
          <div className="proposed-calls">
            <h4>Proposed API Calls:</h4>
            {message.metadata.proposedCalls.map((call, index) => (
              <div key={index} className="proposed-call">
                <div className="call-method">{call.method}</div>
                <div className="call-endpoint">{call.endpoint}</div>
                {call.parameters && (
                  <div className="call-parameters">
                    <pre>{JSON.stringify(call.parameters, null, 2)}</pre>
                  </div>
                )}
              </div>
            ))}
            <div className="call-actions">
              <button className="button button-primary">Review & Execute</button>
              <button className="button button-secondary">Modify</button>
              <button className="button button-outline">Cancel</button>
            </div>
          </div>
        </div>
      );
    }

    // Check if content is structured data
    try {
      const parsed = JSON.parse(message.content);
      if (Array.isArray(parsed)) {
        return formatAsTable(parsed);
      }
    } catch {
      // Not JSON, render as formatted text
    }

    return (
      <div 
        className="message-text"
        dangerouslySetInnerHTML={formatNetworkData(message.content)}
      />
    );
  };

  return (
    <div className="message-list" role="log" aria-live="polite">
      {messages.map((message) => (
        <div
          key={message.id}
          className={`message message-${message.sender} message-${message.messageType}`}
          role="article"
          aria-label={`${message.sender} message at ${formatTimestamp(message.timestamp)}`}
        >
          <div className="message-header">
            <div className="message-sender">
              {message.sender === 'user' && (
                <div className="sender-avatar user-avatar">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="10" cy="7" r="3" stroke="currentColor" strokeWidth="1.5"/>
                    <path d="M4 18c0-4 2.5-6 6-6s6 2 6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                  </svg>
                </div>
              )}
              {message.sender === 'assistant' && (
                <div className="sender-avatar assistant-avatar">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <rect x="3" y="3" width="14" height="10" rx="2" stroke="currentColor" strokeWidth="1.5"/>
                    <path d="M7 7h6M7 10h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                    <path d="M8 13l2 2 2-2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </div>
              )}
              {message.sender === 'system' && (
                <div className="sender-avatar system-avatar">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.5"/>
                    <path d="M10 6v4l2 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </div>
              )}
              <span className="sender-name">
                {message.sender === 'user' ? 'You' : 
                 message.sender === 'assistant' ? 'Infoblox AI' : 'System'}
              </span>
            </div>
            <div className="message-timestamp">
              {formatTimestamp(message.timestamp)}
            </div>
            {message.metadata?.confidence && (
              <div className="message-confidence">
                <span className="confidence-label">Confidence:</span>
                <div className="confidence-bar">
                  <div 
                    className="confidence-fill"
                    style={{ width: `${message.metadata.confidence * 100}%` }}
                  />
                </div>
                <span className="confidence-value">
                  {Math.round(message.metadata.confidence * 100)}%
                </span>
              </div>
            )}
          </div>
          
          <div className="message-content">
            {renderMessageContent(message)}
          </div>
          
          {message.messageType === 'error' && (
            <div className="message-error-details">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5"/>
                <path d="M8 4v4M8 12h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
              <span>This message indicates an error occurred</span>
            </div>
          )}
        </div>
      ))}
      
      {isLoading && (
        <div className="message message-assistant message-loading" role="status" aria-label="AI is thinking">
          <div className="message-header">
            <div className="message-sender">
              <div className="sender-avatar assistant-avatar">
                <LoadingSpinner size="small" />
              </div>
              <span className="sender-name">Infoblox AI</span>
            </div>
          </div>
          <div className="message-content">
            <div className="typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>
            <span className="loading-text">Processing your request...</span>
          </div>
        </div>
      )}
    </div>
  );
};

export default MessageList;