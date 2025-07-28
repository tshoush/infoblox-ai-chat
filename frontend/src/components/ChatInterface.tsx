import React, { useState, useEffect, useCallback, useRef } from 'react';
import { v4 as uuidv4 } from 'uuid';
import MessageList from './MessageList';
import InputField from './InputField';
import Header from './Header';
import StatusIndicator from './StatusIndicator';
import './ChatInterface.css';

export interface ChatMessage {
  id: string;
  content: string;
  sender: 'user' | 'assistant' | 'system';
  timestamp: Date;
  messageType: 'text' | 'api_call' | 'result' | 'error';
  metadata?: {
    proposedCalls?: any[];
    confidence?: number;
    sessionId?: string;
    requestId?: string;
  };
}

export interface SystemStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  infobloxConnected: boolean;
  llmConnected: boolean;
  lastChecked: Date;
}

const ChatInterface: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId] = useState(() => uuidv4());
  const [systemStatus, setSystemStatus] = useState<SystemStatus>({
    status: 'healthy',
    infobloxConnected: true,
    llmConnected: true,
    lastChecked: new Date()
  });
  const [error, setError] = useState<string | null>(null);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const retryTimeoutRef = useRef<NodeJS.Timeout>();

  // Auto-scroll to bottom when new messages arrive
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Check system status periodically
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const response = await fetch('/health');
        const healthData = await response.json();
        
        setSystemStatus({
          status: healthData.status,
          infobloxConnected: healthData.checks?.infoblox_connection === 'pass',
          llmConnected: true, // Will be updated when LLM integration is implemented
          lastChecked: new Date()
        });
        
        // Clear any existing errors if system is healthy
        if (healthData.status === 'healthy' && error) {
          setError(null);
        }
      } catch (err) {
        console.error('Health check failed:', err);
        setSystemStatus(prev => ({
          ...prev,
          status: 'unhealthy',
          lastChecked: new Date()
        }));
      }
    };

    // Initial check
    checkStatus();
    
    // Check every 30 seconds
    const interval = setInterval(checkStatus, 30000);
    
    return () => clearInterval(interval);
  }, [error]);

  // Add welcome message on component mount
  useEffect(() => {
    const welcomeMessage: ChatMessage = {
      id: uuidv4(),
      content: 'Welcome to the Infoblox AI Chat Interface! I can help you manage your network infrastructure using natural language. Try asking me to "show all A records" or "list networks".',
      sender: 'assistant',
      timestamp: new Date(),
      messageType: 'text',
      metadata: {
        sessionId
      }
    };
    
    setMessages([welcomeMessage]);
  }, [sessionId]);

  const handleSendMessage = useCallback(async (message: string) => {
    if (!message.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      id: uuidv4(),
      content: message.trim(),
      sender: 'user',
      timestamp: new Date(),
      messageType: 'text',
      metadata: { sessionId }
    };

    setMessages(prev => [...prev, userMessage]);
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Session-ID': sessionId
        },
        body: JSON.stringify({ message: message.trim() })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error?.message || `HTTP ${response.status}`);
      }

      const data = await response.json();
      
      const assistantMessage: ChatMessage = {
        id: uuidv4(),
        content: data.response,
        sender: 'assistant',
        timestamp: new Date(data.timestamp),
        messageType: data.proposed_calls?.length > 0 ? 'api_call' : 'text',
        metadata: {
          proposedCalls: data.proposed_calls,
          confidence: data.confidence,
          sessionId: data.session_id,
          requestId: data.request_id
        }
      };

      setMessages(prev => [...prev, assistantMessage]);

    } catch (err) {
      console.error('Chat request failed:', err);
      
      const errorMessage: ChatMessage = {
        id: uuidv4(),
        content: `I'm sorry, I encountered an error: ${err instanceof Error ? err.message : 'Unknown error'}. Please try again.`,
        sender: 'system',
        timestamp: new Date(),
        messageType: 'error',
        metadata: { sessionId }
      };

      setMessages(prev => [...prev, errorMessage]);
      setError(err instanceof Error ? err.message : 'Unknown error occurred');
      
      // Implement retry logic
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
      }
      
      retryTimeoutRef.current = setTimeout(() => {
        setError(null);
      }, 5000);

    } finally {
      setIsLoading(false);
    }
  }, [isLoading, sessionId]);

  const handleRetry = useCallback(() => {
    setError(null);
    // Could implement retry of last failed message here
  }, []);

  const handleClearChat = useCallback(() => {
    setMessages([]);
    setError(null);
    
    // Add new welcome message
    const welcomeMessage: ChatMessage = {
      id: uuidv4(),
      content: 'Chat cleared. How can I help you manage your Infoblox infrastructure?',
      sender: 'assistant',
      timestamp: new Date(),
      messageType: 'text',
      metadata: { sessionId }
    };
    
    setMessages([welcomeMessage]);
  }, [sessionId]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
      }
    };
  }, []);

  return (
    <div className="chat-interface" role="main" aria-label="Infoblox AI Chat Interface">
      <Header 
        systemStatus={systemStatus}
        onClearChat={handleClearChat}
        sessionId={sessionId}
      />
      
      <div className="chat-container">
        <div className="chat-messages" role="log" aria-live="polite" aria-label="Chat messages">
          <MessageList 
            messages={messages}
            isLoading={isLoading}
          />
          <div ref={messagesEndRef} />
        </div>
        
        <div className="chat-input-container">
          {error && (
            <div className="error-banner" role="alert">
              <div className="error-content">
                <span className="error-message">{error}</span>
                <button 
                  className="button button-outline error-retry"
                  onClick={handleRetry}
                  aria-label="Retry last action"
                >
                  Retry
                </button>
              </div>
            </div>
          )}
          
          <StatusIndicator 
            status={systemStatus.status}
            lastChecked={systemStatus.lastChecked}
          />
          
          <InputField 
            onSend={handleSendMessage}
            disabled={isLoading || systemStatus.status === 'unhealthy'}
            placeholder={
              systemStatus.status === 'unhealthy' 
                ? 'System unavailable - please wait...'
                : 'Ask me about your Infoblox infrastructure...'
            }
          />
        </div>
      </div>
    </div>
  );
};

export default ChatInterface;