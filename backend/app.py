"""
Flask application foundation for Infoblox AI Chat Interface.
Provides REST API endpoints for chat processing and WAPI operations.
"""

import logging
import time
import os
from datetime import datetime
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from typing import Dict, Any, List
import uuid

from config import config_manager
from tools import test_connection, get_supported_objects
from cache import session_manager, llm_cache
from circuit_breaker import circuit_breaker_manager
from llm_client import llm_client, LLMRequest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Load configuration
config = config_manager.load_config()

# Global metrics storage (in production, use Redis or proper metrics system)
metrics = {
    'requests_total': 0,
    'requests_by_endpoint': {},
    'response_times': [],
    'errors_total': 0,
    'active_sessions': set()
}


@app.before_request
def before_request():
    """Set up request context and metrics."""
    g.start_time = time.time()
    g.request_id = str(uuid.uuid4())
    g.session_id = request.headers.get('X-Session-ID', str(uuid.uuid4()))
    
    # Update metrics
    metrics['requests_total'] += 1
    endpoint = request.endpoint or 'unknown'
    metrics['requests_by_endpoint'][endpoint] = metrics['requests_by_endpoint'].get(endpoint, 0) + 1
    metrics['active_sessions'].add(g.session_id)
    
    logger.info(f"Request {g.request_id} started - {request.method} {request.path}")


@app.after_request
def after_request(response):
    """Log request completion and update metrics."""
    duration = time.time() - g.start_time
    metrics['response_times'].append(duration)
    
    # Keep only last 1000 response times for memory management
    if len(metrics['response_times']) > 1000:
        metrics['response_times'] = metrics['response_times'][-1000:]
    
    logger.info(f"Request {g.request_id} completed - {response.status_code} in {duration:.3f}s")
    return response


@app.errorhandler(Exception)
def handle_error(error):
    """Global error handler with structured error responses."""
    metrics['errors_total'] += 1
    
    error_id = str(uuid.uuid4())
    logger.error(f"Error {error_id} in request {getattr(g, 'request_id', 'unknown')}: {str(error)}")
    
    # Categorize errors
    if isinstance(error, ConnectionError):
        error_type = "connection"
        message = "Failed to connect to external service"
        status_code = 503
    elif isinstance(error, TimeoutError):
        error_type = "timeout"
        message = "Request timed out"
        status_code = 504
    elif isinstance(error, ValueError):
        error_type = "validation"
        message = "Invalid request parameters"
        status_code = 400
    else:
        error_type = "internal"
        message = "An unexpected error occurred"
        status_code = 500
    
    return jsonify({
        'error': {
            'id': error_id,
            'type': error_type,
            'message': message,
            'timestamp': datetime.utcnow().isoformat(),
            'request_id': getattr(g, 'request_id', None)
        }
    }), status_code


# Health and Status Endpoints

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for load balancers and monitoring."""
    try:
        # Test basic functionality
        config_valid = len(config_manager.validate_config()) == 0
        
        # Test Infoblox connectivity (with timeout)
        try:
            infoblox_connected = test_connection()
        except Exception:
            infoblox_connected = False
        
        health_status = {
            'status': 'healthy' if config_valid and infoblox_connected else 'degraded',
            'timestamp': datetime.utcnow().isoformat(),
            'version': '1.0.0',
            'checks': {
                'configuration': 'pass' if config_valid else 'fail',
                'infoblox_connection': 'pass' if infoblox_connected else 'fail'
            }
        }
        
        status_code = 200 if health_status['status'] == 'healthy' else 503
        return jsonify(health_status), status_code
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.utcnow().isoformat(),
            'error': str(e)
        }), 503


@app.route('/status', methods=['GET'])
def status():
    """Detailed status endpoint with metrics."""
    try:
        avg_response_time = sum(metrics['response_times']) / len(metrics['response_times']) if metrics['response_times'] else 0
        
        return jsonify({
            'status': 'operational',
            'timestamp': datetime.utcnow().isoformat(),
            'metrics': {
                'requests_total': metrics['requests_total'],
                'errors_total': metrics['errors_total'],
                'active_sessions': len(metrics['active_sessions']),
                'avg_response_time': round(avg_response_time, 3),
                'endpoints': metrics['requests_by_endpoint']
            },
            'configuration': {
                'infoblox_grid': config.infoblox.grid_ip,
                'llm_provider': config.llm.provider,
                'cache_enabled': config.cache.enable_cache,
                'max_concurrent_users': config.performance.max_concurrent_users
            },
            'supported_objects': get_supported_objects(),
            'circuit_breakers': circuit_breaker_manager.get_all_states(),
            'llm_status': llm_client.get_provider_status()
        })
        
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return jsonify({
            'status': 'error',
            'timestamp': datetime.utcnow().isoformat(),
            'error': str(e)
        }), 500


@app.route('/metrics', methods=['GET'])
def metrics_endpoint():
    """Prometheus-style metrics endpoint."""
    try:
        avg_response_time = sum(metrics['response_times']) / len(metrics['response_times']) if metrics['response_times'] else 0
        
        prometheus_metrics = f'''# HELP iaci_requests_total Total number of requests
# TYPE iaci_requests_total counter
iaci_requests_total {metrics['requests_total']}

# HELP iaci_errors_total Total number of errors
# TYPE iaci_errors_total counter
iaci_errors_total {metrics['errors_total']}

# HELP iaci_active_sessions Current number of active sessions
# TYPE iaci_active_sessions gauge
iaci_active_sessions {len(metrics['active_sessions'])}

# HELP iaci_response_time_seconds Average response time in seconds
# TYPE iaci_response_time_seconds gauge
iaci_response_time_seconds {avg_response_time}
'''
        
        return prometheus_metrics, 200, {'Content-Type': 'text/plain'}
        
    except Exception as e:
        logger.error(f"Metrics endpoint failed: {e}")
        return f"# Error generating metrics: {e}", 500, {'Content-Type': 'text/plain'}


# API Endpoints (Stubs for now - will be implemented in later tasks)

@app.route('/api/chat', methods=['POST'])
def chat():
    """Process chat messages and return AI responses."""
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'Message is required'}), 400
        
        message = data['message']
        session_id = g.session_id
        
        # Get or create session
        session_data = session_manager.get_session(session_id)
        if not session_data:
            session_manager.create_session()
            session_data = session_manager.get_session(session_id)
        
        # Update session activity
        session_manager.update_session(session_id, {
            'message_count': session_data.get('message_count', 0) + 1
        })
        
        # Create LLM request
        llm_request = LLMRequest(
            prompt=llm_client.format_prompt_for_wapi(message, session_data.get('context', {})),
            context=session_data.get('context', {}),
            temperature=0.7,
            max_tokens=2000
        )
        
        # Process with LLM
        try:
            llm_response = llm_client.send_request(llm_request)
            
            # Parse the response for WAPI operations
            parsed_response = llm_client.parse_wapi_response(llm_response.content)
            
            # Generate proposed API calls based on parsed response
            proposed_calls = []
            if parsed_response.get('intent') != 'unknown' and parsed_response.get('object_type') != 'unknown':
                proposed_calls.append({
                    'id': str(uuid.uuid4()),
                    'method': _intent_to_method(parsed_response.get('intent', 'GET')),
                    'endpoint': f"/wapi/{config.infoblox.wapi_version}/{parsed_response.get('object_type', '')}",
                    'parameters': parsed_response.get('parameters', {}),
                    'description': parsed_response.get('explanation', 'WAPI operation'),
                    'confidence': parsed_response.get('confidence', 0.5)
                })
            
            response = {
                'response': _format_ai_response(llm_response.content, parsed_response),
                'session_id': session_id,
                'timestamp': datetime.utcnow().isoformat(),
                'proposed_calls': proposed_calls,
                'confidence': parsed_response.get('confidence', llm_response.confidence),
                'cached': llm_response.cached,
                'provider': llm_response.provider
            }
            
        except Exception as llm_error:
            logger.warning(f"LLM processing failed: {llm_error}")
            
            # Fallback to basic keyword processing
            response = {
                'response': f"I understand you want to work with: '{message}'. Due to AI service limitations, please try using more specific WAPI commands or try again later.",
                'session_id': session_id,
                'timestamp': datetime.utcnow().isoformat(),
                'proposed_calls': [],
                'confidence': 0.2,
                'cached': False,
                'provider': 'fallback'
            }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        raise


def _intent_to_method(intent: str) -> str:
    """Convert intent to HTTP method."""
    intent_map = {
        'search': 'GET',
        'create': 'POST', 
        'update': 'PUT',
        'delete': 'DELETE'
    }
    return intent_map.get(intent.lower(), 'GET')


def _format_ai_response(raw_response: str, parsed_response: Dict[str, Any]) -> str:
    """Format AI response for user display."""
    if parsed_response.get('intent') == 'unknown':
        return f"I'm not sure how to help with that request. Could you please be more specific about what you'd like to do with your Infoblox infrastructure?"
    
    intent = parsed_response.get('intent', 'unknown')
    object_type = parsed_response.get('object_type', 'unknown')
    explanation = parsed_response.get('explanation', '')
    
    return f"I understand you want to {intent} {object_type.replace('_', ' ')} records. {explanation}"


@app.route('/api/execute', methods=['POST'])
def execute():
    """Execute approved API calls."""
    try:
        data = request.get_json()
        if not data or 'calls' not in data:
            return jsonify({'error': 'API calls are required'}), 400
        
        calls = data['calls']
        
        # TODO: Implement API call execution (Task 3.4)
        # For now, return a placeholder response
        response = {
            'results': [{'status': 'pending', 'message': 'Execution will be implemented in Task 3.4'} for _ in calls],
            'session_id': g.session_id,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Execute endpoint error: {e}")
        raise


@app.route('/api/suggestions', methods=['GET'])
def suggestions():
    """Get auto-suggestions for user input."""
    try:
        query = request.args.get('q', '')
        
        # TODO: Implement suggestion system (Task 3.5)
        # For now, return basic suggestions
        suggestions_list = [
            {'text': 'Show all A records', 'type': 'query'},
            {'text': 'List networks', 'type': 'query'},
            {'text': 'Find host records', 'type': 'query'},
            {'text': 'Create DNS record', 'type': 'action'},
            {'text': 'Search by IP address', 'type': 'query'}
        ]
        
        # Filter suggestions based on query
        if query:
            suggestions_list = [s for s in suggestions_list if query.lower() in s['text'].lower()]
        
        return jsonify({
            'suggestions': suggestions_list[:10],  # Limit to 10 suggestions
            'query': query,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Suggestions endpoint error: {e}")
        raise


@app.route('/api/schema/<object_name>', methods=['GET'])
def get_object_schema(object_name):
    """Get WAPI object schema information."""
    try:
        from tools import get_schema
        
        schema = get_schema(object_name)
        return jsonify({
            'object': object_name,
            'schema': schema,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Schema endpoint error for {object_name}: {e}")
        raise


if __name__ == '__main__':
    # Validate configuration on startup
    config_errors = config_manager.validate_config()
    if config_errors:
        logger.warning(f"Configuration issues detected: {config_errors}")
    
    # Log startup information
    logger.info(f"Starting Infoblox AI Chat Interface")
    logger.info(f"Infoblox Grid: {config.infoblox.grid_ip}")
    logger.info(f"LLM Provider: {config.llm.provider}")
    logger.info(f"Cache Enabled: {config.cache.enable_cache}")
    
    # Start Flask development server
    port = int(os.environ.get('PORT', 5002))
    app.run(
        host='0.0.0.0',
        port=port,
        debug=True,
        threaded=True
    )