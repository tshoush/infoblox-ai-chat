# Infoblox AI Chat Interface (IACI)

An intelligent chat interface that bridges natural language interaction with Infoblox NIOS Web API (WAPI) operations. The system enables network administrators to manage their Infoblox infrastructure using conversational AI, eliminating the need to learn complex API syntax.

## Features

- **Natural Language Processing**: Convert plain English queries into precise WAPI operations
- **Dynamic Tool Generation**: Automatically discover and generate tools for all supported WAPI objects
- **User Approval Workflow**: Review and edit proposed API calls before execution for safety and accuracy
- **RAG-Enhanced Documentation**: Leverage comprehensive Infoblox documentation for intelligent responses
- **Multi-LLM Support**: Compatible with OpenAI, Claude, Grok, Llama, and Gemini providers
- **Marriott-Inspired UI**: Professional, accessible interface with responsive design

## Architecture

- **Backend**: Python Flask with dynamic WAPI tool generation
- **Frontend**: React with Marriott-inspired design system
- **AI Processing**: Multi-provider LLM integration with RAG system
- **Documentation**: Comprehensive requirements, design, and implementation specifications

## Project Structure

```
.kiro/specs/infoblox-ai-chat/
├── requirements.md    # Detailed requirements with EARS format
├── design.md         # Comprehensive system design
└── tasks.md          # Implementation plan with 7 phases
```

## Getting Started

1. Review the requirements document for system capabilities
2. Study the design document for architecture details
3. Follow the implementation plan in tasks.md for development

## Target Users

- Network administrators managing Infoblox NIOS systems
- DevOps engineers automating network infrastructure
- IT professionals seeking simplified WAPI interaction

## Technology Stack

- **Backend**: Flask 3.0.3, Python 3.12
- **Frontend**: React 18.3.1 with react-autosuggest
- **AI**: Multi-provider LLM support (OpenAI, Claude, Grok, Llama, Gemini)
- **Documentation**: RAG system with PDF, YAML, and HTML sources
- **Deployment**: Docker with production optimization

## Development Phases

1. **Foundation**: Project structure and core infrastructure
2. **Backend Services**: API, RAG system, and AI processing
3. **AI Integration**: LLM processing and intent recognition
4. **Frontend UI**: React components with Marriott design
5. **Advanced Features**: Performance optimization and accessibility
6. **Testing**: Comprehensive test suite with CI/CD
7. **Production**: Deployment, monitoring, and documentation

## License

This project is part of a specification-driven development approach for enterprise network management automation.