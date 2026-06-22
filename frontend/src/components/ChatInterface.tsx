import React, { useState, useEffect } from 'react';
import { useChat } from '../ChatContext';
import ProviderSettings from './ProviderSettings';
import '../App.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

// Monotonic, collision-free message ids (Date.now() alone collides within a ms).
let _msgSeq = 0;
const uid = () => `msg-${Date.now()}-${++_msgSeq}`;

// fetch with a hard timeout so a hung backend can't lock the UI forever.
async function fetchWithTimeout(url: string, opts: RequestInit = {}, ms = 30000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { ...opts, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

const ChatInterface: React.FC = () => {
  const { state, dispatch } = useChat();
  const [input, setInput] = useState('');
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    // The session id is seeded synchronously in the reducer; only generate one
    // here as a belt-and-suspenders fallback (never on the first render path).
    if (!state.sessionId) {
      dispatch({ type: 'SET_SESSION_ID', payload: `session-${Date.now()}-${Math.random().toString(36).slice(2)}` });
    }
  }, [state.sessionId, dispatch]);

  const handleSendMessage = async () => {
    if (input.trim() === '') return;

    const newMessage = {
      id: uid(),
      content: input,
      sender: 'user' as const,
      timestamp: Date.now(),
      message_type: 'text' as const,
    };

    dispatch({ type: 'ADD_MESSAGE', payload: newMessage });
    dispatch({ type: 'SET_LOADING', payload: true });
    setInput('');

    try {
      const res = await fetchWithTimeout(`${API_BASE_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: newMessage.content, session_id: state.sessionId }),
      });

      if (!res.ok) {
        throw new Error(`Server responded with ${res.status}`);
      }

      const data = await res.json();
      if (data.session_id && data.session_id !== state.sessionId) {
        dispatch({ type: 'SET_SESSION_ID', payload: data.session_id });
      }

      const response = data.response || {};
      const isProposal = response.response_type === 'api_call_proposal';
      const isPlan = response.response_type === 'api_call_plan';

      let content: string;
      let metadata: any;
      if (isPlan) {
        const ops = response.operations || [];
        const summary = ops
          .map((o: any, i: number) => `${i + 1}. ${o.method} ${o.operation}`)
          .join('\n');
        content = `Proposed plan — ${ops.length} WAPI calls (in order):\n${summary}\n\n${JSON.stringify(ops, null, 2)}`;
        metadata = { operations: ops };
      } else if (isProposal) {
        content = `Proposed WAPI call:\n${JSON.stringify(response.proposal, null, 2)}`;
        metadata = response.proposal;
      } else {
        content = response.content ?? 'No response.';
        metadata = undefined;
      }

      dispatch({
        type: 'ADD_MESSAGE',
        payload: {
          id: uid(),
          content,
          sender: 'assistant' as const,
          timestamp: Date.now(),
          message_type: isProposal || isPlan ? ('api_call' as const) : ('text' as const),
          metadata,
        },
      });
    } catch (err) {
      dispatch({
        type: 'ADD_MESSAGE',
        payload: {
          id: uid(),
          content: `Sorry, something went wrong: ${err instanceof Error ? err.message : 'unknown error'}`,
          sender: 'assistant' as const,
          timestamp: Date.now(),
          message_type: 'text' as const,
        },
      });
    } finally {
      dispatch({ type: 'SET_LOADING', payload: false });
    }
  };

  const handleExecute = async (proposal: any) => {
    // A plan carries {operations: [...]}; a single call carries the call fields.
    const isPlan = proposal && Array.isArray(proposal.operations);
    const ops = isPlan ? proposal.operations : [proposal];
    const mutates = ops.some((o: any) => (m => m !== 'GET' && m !== 'HEAD')(String(o?.method || '').trim().toUpperCase()));

    if (mutates) {
      const desc = isPlan
        ? `${ops.length} calls (${ops.map((o: any) => `${o.method} ${o.operation}`).join(', ')})`
        : `${ops[0]?.method} ${ops[0]?.operation}`;
      if (!window.confirm(`This will run ${desc} against the Grid. Continue?`)) return;
    }

    dispatch({ type: 'SET_LOADING', payload: true });
    try {
      const res = await fetchWithTimeout(`${API_BASE_URL}/api/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ operations: ops, session_id: state.sessionId }),
      });
      const data = await res.json();
      const results = Array.isArray(data.results) ? data.results : [data];

      const lines = results.map((r: any, i: number) => {
        const op = ops[i] || {};
        const tag = r?.success ? '✓' : '✗';
        const detail = r?.success
          ? JSON.stringify(r.data)
          : (r?.error || `HTTP ${res.status}`);
        return `${tag} ${op.method || ''} ${op.operation || ''}: ${detail}`;
      });
      const header = data.summary
        ? `Executed ${data.summary.succeeded}/${data.summary.total} call(s):`
        : 'Result:';
      const content = `${header}\n${lines.join('\n')}`;

      dispatch({
        type: 'ADD_MESSAGE',
        payload: {
          id: uid(),
          content,
          sender: 'assistant' as const,
          timestamp: Date.now(),
          message_type: 'result' as const,
          metadata: data,
        },
      });
    } catch (err) {
      dispatch({
        type: 'ADD_MESSAGE',
        payload: {
          id: uid(),
          content: `✗ Could not reach the server: ${err instanceof Error ? err.message : 'unknown error'}`,
          sender: 'assistant' as const,
          timestamp: Date.now(),
          message_type: 'result' as const,
        },
      });
    } finally {
      dispatch({ type: 'SET_LOADING', payload: false });
    }
  };

  return (
    <div className="chat-interface">
      <header className="chat-header">
        <h1>Infoblox AI Chat</h1>
        <button
          className="settings-button"
          onClick={() => setShowSettings(true)}
          aria-label="LLM provider settings"
          title="LLM provider settings"
        >
          ⚙
        </button>
      </header>
      {showSettings && <ProviderSettings onClose={() => setShowSettings(false)} />}
      <div className="message-list">
        {state.messages.map((message) => (
          <div key={message.id} className={`message-${message.sender}`}>
            <pre className="message-content">{message.content}</pre>
            {message.message_type === 'api_call' && message.metadata && (
              <button
                className="button-execute"
                onClick={() => handleExecute(message.metadata)}
                disabled={state.isLoading}
                aria-label="Execute proposed WAPI call"
              >
                {Array.isArray(message.metadata.operations)
                  ? `▶ Run all ${message.metadata.operations.length} calls`
                  : '▶ Run this call'}
              </button>
            )}
          </div>
        ))}
        {state.isLoading && (
          <div className="message-assistant">
            <p>Thinking...</p>
          </div>
        )}
      </div>
      <div className="input-field-container">
        <input
          type="text"
          placeholder="Type your message..."
          className="input-field"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={(e) => {
            if (e.key === 'Enter') {
              handleSendMessage();
            }
          }}
          disabled={state.isLoading}
        />
        <button onClick={handleSendMessage} className="button-primary" disabled={state.isLoading}>
          Send
        </button>
      </div>
    </div>
  );
};

export default ChatInterface;