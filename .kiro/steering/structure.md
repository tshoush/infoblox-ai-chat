# Project Structure

## Root Directory Layout

```
iaci/                           # Main project directory (created by setup.sh)
├── backend/                    # Python Flask backend
│   ├── app.py                 # Main Flask application
│   ├── tools.py               # Auto-generated WAPI tools
│   ├── config.json            # Configuration (credentials, LLM settings)
│   ├── requirements.txt       # Python dependencies
│   └── tests/                 # Backend test suite
│       └── test_tools.py      # Tool testing
├── frontend/                  # React frontend application
│   ├── src/
│   │   └── components/        # React components
│   │       └── Chat.js        # Main chat interface
│   ├── public/
│   │   └── index.html         # HTML entry point
│   └── package.json           # Frontend dependencies
├── rag_docs/                  # Documentation for RAG system
│   ├── wapi_guide.pdf         # Official Infoblox WAPI guide
│   ├── swagger.yaml           # WAPI Swagger specification
│   └── wapi_doc.html          # Additional HTML documentation
├── schema.json                # Main WAPI schema
├── schema_*.json              # Object-specific schemas
├── vocabulary.json            # Domain vocabulary (updated at runtime)
└── Dockerfile                 # Container configuration
```

## Backend Architecture

### Core Modules (Planned)
- `app.py` - Flask application with chat endpoints
- `config.py` - Configuration management
- `tool_generator.py` - Dynamic WAPI tool generation
- `ai_processor.py` - Natural language processing
- `rag_system.py` - Documentation retrieval system
- `vocabulary.py` - Domain vocabulary management

### Generated Files
- `tools.py` - Auto-generated functions for each WAPI object
- `config.json` - Runtime configuration from setup.sh
- `schema_*.json` - Individual object schemas from WAPI

## Frontend Architecture

### Component Structure (Planned)
- `ChatInterface` - Main chat container
- `MessageList` - Message history display
- `InputField` - User input with auto-suggestions
- `APICallReview` - Review/edit proposed API calls
- `LoadingSpinner` - Loading states
- `StatusIndicator` - System status feedback

### Styling Approach
- Marriott-inspired design system
- CSS variables for consistent theming
- Responsive mobile-first design
- Component-scoped styling

## Configuration Files

### Backend Configuration (`backend/config.json`)
```json
{
  "infoblox": {
    "grid_ip": "...",
    "admin_user": "...",
    "network_view": "default"
  },
  "llm": {
    "provider": "...",
    "api_key": "...",
    "base_url": "..."
  }
}
```

### Dependencies
- `backend/requirements.txt` - Python packages
- `frontend/package.json` - Node.js packages

## Data Flow

1. **Setup Phase**: `setup.sh` creates directory structure, fetches schemas, generates tools
2. **Runtime Phase**: Flask serves API endpoints, React provides UI
3. **Processing**: User input → AI processing → WAPI calls → Results display

## Key Conventions

- **Auto-generation**: Tools and schemas are dynamically created from WAPI discovery
- **Security**: Credentials stored in config.json, not in code
- **Modularity**: Clear separation between frontend, backend, and external services
- **Documentation**: RAG system uses multiple documentation sources
- **Testing**: Separate test directories for backend and frontend