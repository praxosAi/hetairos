from typing import Dict, Optional

class ErrorClassifier:
    """Classifies errors from search operations to provide user-friendly responses"""
    
    def classify_error(self, error_message: str, search_query: str, search_context: Dict = None) -> Dict:
        """
        Classify an error message and determine how to respond to the user
        
        Args:
            error_message: The error message from the search operation
            search_query: The user's original search query
            search_context: Additional context about the search
            
        Returns:
            Dict with error classification information
        """
        error_message_lower = error_message.lower()
        
        # Technical errors that can be made user-friendly
        if any(phrase in error_message_lower for phrase in [
            "function missing required argument",
            "missing required parameter",
            "invalid parameter",
            "argument error"
        ]):
            return {
                'type': 'technical',
                'category': 'search_parameter_error',
                'user_friendly': True,
                'requires_source_suggestion': True,
                'severity': 'medium'
            }
        
        # Content not found errors
        if any(phrase in error_message_lower for phrase in [
            "no results found",
            "no matches",
            "nothing found",
            "empty result",
            "no data available"
        ]):
            return {
                'type': 'not_found',
                'category': 'content_missing',
                'user_friendly': True,
                'requires_source_suggestion': True,
                'severity': 'low'
            }
        
        # Permission/authentication errors
        if any(phrase in error_message_lower for phrase in [
            "permission denied",
            "unauthorized",
            "access denied",
            "authentication failed",
            "forbidden"
        ]):
            return {
                'type': 'permission',
                'category': 'access_denied',
                'user_friendly': True,
                'requires_source_suggestion': False,
                'severity': 'high'
            }
        
        # Rate limiting errors
        if any(phrase in error_message_lower for phrase in [
            "rate limit",
            "too many requests",
            "quota exceeded",
            "throttled"
        ]):
            return {
                'type': 'rate_limit',
                'category': 'service_limit',
                'user_friendly': True,
                'requires_source_suggestion': False,
                'severity': 'medium'
            }
        
        # Network/connectivity errors
        if any(phrase in error_message_lower for phrase in [
            "connection timeout",
            "network error",
            "service unavailable",
            "connection failed"
        ]):
            return {
                'type': 'network',
                'category': 'connectivity_issue',
                'user_friendly': True,
                'requires_source_suggestion': False,
                'severity': 'high'
            }
        
        # Database/storage errors
        if any(phrase in error_message_lower for phrase in [
            "database error",
            "storage error",
            "data corruption",
            "index error"
        ]):
            return {
                'type': 'storage',
                'category': 'data_issue',
                'user_friendly': False,
                'requires_source_suggestion': False,
                'severity': 'high'
            }
        
        # Unknown/system errors
        return {
            'type': 'unknown',
            'category': 'system_error',
            'user_friendly': False,
            'requires_source_suggestion': False,
            'severity': 'high'
        }
    
    def should_suggest_sources(self, error_classification: Dict, search_query: str) -> bool:
        """
        Determine if we should suggest available sources based on error type and query
        
        Args:
            error_classification: Result from classify_error
            search_query: The user's search query
            
        Returns:
            True if we should suggest sources, False otherwise
        """
        # Always suggest sources if the classification indicates it
        if error_classification.get('requires_source_suggestion', False):
            return True
        
        # For certain query types, we might want to suggest sources even if not required
        health_keywords = ['health', 'medical', 'doctor', 'medication', 'symptoms', 'cholesterol', 'blood', 'test']
        if any(keyword in search_query.lower() for keyword in health_keywords):
            return True
        
        # For personal data queries
        personal_keywords = ['my', 'i', 'me', 'personal', 'private']
        if any(keyword in search_query.lower() for keyword in personal_keywords):
            return True
        
        return False
    
    def get_error_priority(self, error_classification: Dict) -> int:
        """
        Get the priority level for handling this error (1=high, 3=low)
        
        Args:
            error_classification: Result from classify_error
            
        Returns:
            Priority level (1-3)
        """
        severity_map = {
            'high': 1,
            'medium': 2,
            'low': 3
        }
        
        return severity_map.get(error_classification.get('severity', 'high'), 1)
    
    def get_suggested_actions(self, error_classification: Dict, search_query: str) -> list:
        """
        Get suggested actions based on error type
        
        Args:
            error_classification: Result from classify_error
            search_query: The user's search query
            
        Returns:
            List of suggested actions
        """
        error_type = error_classification.get('type', 'unknown')
        
        if error_type == 'technical':
            return [
                "Try rephrasing your question",
                "Specify which source to search (e.g., 'Check my Gmail')",
                "Be more specific about what you're looking for"
            ]
        
        elif error_type == 'not_found':
            return [
                "Check if the information exists in your connected sources",
                "Try different keywords",
                "Add more integrations at app.mypraxos.com"
            ]
        
        elif error_type == 'permission':
            return [
                "Check your integration permissions",
                "Reconnect the integration at app.mypraxos.com",
                "Contact support if the issue persists"
            ]
        
        elif error_type == 'rate_limit':
            return [
                "Wait a few minutes and try again",
                "Try searching for something else first",
                "Contact support if this happens frequently"
            ]
        
        elif error_type == 'network':
            return [
                "Check your internet connection",
                "Try again in a few minutes",
                "Contact support if the issue persists"
            ]
        
        else:
            return [
                "Try again in a few minutes",
                "Contact support if the issue persists"
            ]