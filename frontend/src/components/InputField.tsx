import React, { useState, useRef, useCallback, useEffect } from 'react';
import Autosuggest from 'react-autosuggest';
import './InputField.css';

interface Suggestion {
  text: string;
  type: 'query' | 'action' | 'entity';
  description?: string;
}

interface InputFieldProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

const InputField: React.FC<InputFieldProps> = ({ 
  onSend, 
  disabled = false, 
  placeholder = "Ask me about your Infoblox infrastructure..." 
}) => {
  const [value, setValue] = useState('');
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [isLoadingSuggestions, setIsLoadingSuggestions] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<NodeJS.Timeout>();

  // Focus input on component mount
  useEffect(() => {
    if (inputRef.current && !disabled) {
      inputRef.current.focus();
    }
  }, [disabled]);

  // Debounced suggestion fetching
  const fetchSuggestions = useCallback(async (query: string) => {
    if (query.length < 2) {
      setSuggestions([]);
      return;
    }

    setIsLoadingSuggestions(true);
    
    try {
      const response = await fetch(`/api/suggestions?q=${encodeURIComponent(query)}`);
      if (response.ok) {
        const data = await response.json();
        setSuggestions(data.suggestions || []);
      }
    } catch (error) {
      console.error('Failed to fetch suggestions:', error);
      // Provide fallback suggestions
      setSuggestions(getFallbackSuggestions(query));
    } finally {
      setIsLoadingSuggestions(false);
    }
  }, []);

  const getFallbackSuggestions = (query: string): Suggestion[] => {
    const fallbackSuggestions: Suggestion[] = [
      { text: 'Show all A records', type: 'query', description: 'List all A records in the system' },
      { text: 'List networks', type: 'query', description: 'Display all configured networks' },
      { text: 'Find host records', type: 'query', description: 'Search for host records' },
      { text: 'Show DNS zones', type: 'query', description: 'List all DNS zones' },
      { text: 'Create A record', type: 'action', description: 'Create a new A record' },
      { text: 'Search by IP address', type: 'query', description: 'Find records by IP address' },
      { text: 'Show DHCP ranges', type: 'query', description: 'List DHCP ranges' },
      { text: 'Find CNAME records', type: 'query', description: 'Search for CNAME records' },
      { text: 'List network views', type: 'query', description: 'Show all network views' },
      { text: 'Show grid members', type: 'query', description: 'Display grid member information' }
    ];

    return fallbackSuggestions.filter(suggestion =>
      suggestion.text.toLowerCase().includes(query.toLowerCase())
    ).slice(0, 8);
  };

  const onSuggestionsFetchRequested = useCallback(({ value }: { value: string }) => {
    // Clear existing timeout
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    // Debounce the API call
    debounceRef.current = setTimeout(() => {
      fetchSuggestions(value);
    }, 300);
  }, [fetchSuggestions]);

  const onSuggestionsClearRequested = useCallback(() => {
    setSuggestions([]);
  }, []);

  const getSuggestionValue = (suggestion: Suggestion) => suggestion.text;

  const renderSuggestion = (suggestion: Suggestion, { isHighlighted }: { isHighlighted: boolean }) => (
    <div className={`suggestion ${isHighlighted ? 'suggestion-highlighted' : ''}`}>
      <div className="suggestion-content">
        <div className="suggestion-text">{suggestion.text}</div>
        {suggestion.description && (
          <div className="suggestion-description">{suggestion.description}</div>
        )}
      </div>
      <div className={`suggestion-type suggestion-type-${suggestion.type}`}>
        {suggestion.type === 'query' && (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.5"/>
            <path d="m13 13-3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
        )}
        {suggestion.type === 'action' && (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M8 2v12M2 8h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
        )}
        {suggestion.type === 'entity' && (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="2" y="2" width="12" height="12" rx="2" stroke="currentColor" strokeWidth="1.5"/>
            <path d="M6 6h4M6 10h2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
        )}
      </div>
    </div>
  );

  const renderSuggestionsContainer = ({ containerProps, children }: any) => (
    <div {...containerProps} className="suggestions-container">
      {isLoadingSuggestions && (
        <div className="suggestions-loading">
          <div className="loading-spinner" />
          <span>Loading suggestions...</span>
        </div>
      )}
      {children}
    </div>
  );

  const onChange = (_: any, { newValue }: { newValue: string }) => {
    setValue(newValue);
  };

  const onSuggestionSelected = (_: any, { suggestion }: { suggestion: Suggestion }) => {
    setValue(suggestion.text);
    // Auto-send if it's a complete query
    if (suggestion.type === 'query') {
      setTimeout(() => handleSend(suggestion.text), 100);
    }
  };

  const handleSend = useCallback((message?: string) => {
    const messageToSend = message || value.trim();
    if (messageToSend && !disabled) {
      onSend(messageToSend);
      setValue('');
      setSuggestions([]);
    }
  }, [value, disabled, onSend]);

  const handleKeyPress = useCallback((event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  const handleSubmit = useCallback((event: React.FormEvent) => {
    event.preventDefault();
    handleSend();
  }, [handleSend]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  const inputProps = {
    placeholder,
    value,
    onChange,
    onKeyPress: handleKeyPress,
    disabled,
    className: 'input-field',
    'aria-label': 'Message input',
    'aria-describedby': 'input-help',
    ref: inputRef
  };

  return (
    <form className="input-container" onSubmit={handleSubmit} role="search">
      <div className="input-wrapper">
        <Autosuggest
          suggestions={suggestions}
          onSuggestionsFetchRequested={onSuggestionsFetchRequested}
          onSuggestionsClearRequested={onSuggestionsClearRequested}
          getSuggestionValue={getSuggestionValue}
          renderSuggestion={renderSuggestion}
          renderSuggestionsContainer={renderSuggestionsContainer}
          onSuggestionSelected={onSuggestionSelected}
          inputProps={inputProps}
          theme={{
            container: 'autosuggest-container',
            input: 'autosuggest-input',
            suggestionsContainer: 'autosuggest-suggestions-container',
            suggestionsList: 'autosuggest-suggestions-list',
            suggestion: 'autosuggest-suggestion',
            suggestionHighlighted: 'autosuggest-suggestion-highlighted'
          }}
        />
        
        <button
          type="submit"
          className="send-button"
          disabled={disabled || !value.trim()}
          aria-label="Send message"
          title="Send message (Enter)"
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M18 2L9 11M18 2l-7 16-2-7-7-2L18 2z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      </div>
      
      <div id="input-help" className="input-help">
        <div className="help-text">
          <span>Press Enter to send, Shift+Enter for new line</span>
          {suggestions.length > 0 && (
            <span className="suggestions-count">
              {suggestions.length} suggestion{suggestions.length !== 1 ? 's' : ''} available
            </span>
          )}
        </div>
        
        <div className="quick-actions">
          <button
            type="button"
            className="quick-action"
            onClick={() => handleSend('Show all A records')}
            disabled={disabled}
            title="Quick action: Show all A records"
          >
            A Records
          </button>
          <button
            type="button"
            className="quick-action"
            onClick={() => handleSend('List networks')}
            disabled={disabled}
            title="Quick action: List networks"
          >
            Networks
          </button>
          <button
            type="button"
            className="quick-action"
            onClick={() => handleSend('Show DNS zones')}
            disabled={disabled}
            title="Quick action: Show DNS zones"
          >
            DNS Zones
          </button>
        </div>
      </div>
    </form>
  );
};

export default InputField;