import React, { createContext, useReducer, ReactNode, useContext } from 'react';

// Define the shape of a chat message
interface ChatMessage {
  id: string;
  content: string;
  sender: 'user' | 'assistant';
  timestamp: number;
  message_type: 'text' | 'api_call' | 'result';
  metadata?: any;
}

// Define the shape of the chat state
interface ChatState {
  messages: ChatMessage[];
  isLoading: boolean;
  currentInput: string;
  sessionId: string | null;
}

// Define action types
type ChatAction =
  | { type: 'ADD_MESSAGE'; payload: ChatMessage }
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_CURRENT_INPUT'; payload: string }
  | { type: 'SET_SESSION_ID'; payload: string };

// A session id seeded synchronously so the very first message isn't sent with
// session_id: null (the backend will adopt this id, keeping context stable).
const newSessionId = () =>
  (typeof crypto !== 'undefined' && 'randomUUID' in crypto)
    ? `session-${crypto.randomUUID()}`
    : `session-${Date.now()}-${Math.random().toString(36).slice(2)}`;

// Initial state
const initialState: ChatState = {
  messages: [],
  isLoading: false,
  currentInput: '',
  sessionId: newSessionId(),
};

// Reducer function
const chatReducer = (state: ChatState, action: ChatAction): ChatState => {
  switch (action.type) {
    case 'ADD_MESSAGE':
      return { ...state, messages: [...state.messages, action.payload] };
    case 'SET_LOADING':
      return { ...state, isLoading: action.payload };
    case 'SET_CURRENT_INPUT':
      return { ...state, currentInput: action.payload };
    case 'SET_SESSION_ID':
      return { ...state, sessionId: action.payload };
    default:
      return state;
  }
};

// Create the context
interface ChatContextType {
  state: ChatState;
  dispatch: React.Dispatch<ChatAction>;
}

export const ChatContext = createContext<ChatContextType | undefined>(undefined);

// Create a provider component
interface ChatProviderProps {
  children: ReactNode;
}

export const ChatProvider: React.FC<ChatProviderProps> = ({ children }) => {
  const [state, dispatch] = useReducer(chatReducer, initialState);

  return (
    <ChatContext.Provider value={{ state, dispatch }}>
      {children}
    </ChatContext.Provider>
  );
};

// Custom hook for easy access to chat context
export const useChat = () => {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
};
