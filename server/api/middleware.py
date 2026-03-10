from flask import jsonify, request
from flask_jwt_extended import verify_jwt_in_request
import os

FLASK_ENV = os.environ.get('FLASK_ENV', 'development')
IS_PRODUCTION = FLASK_ENV == 'production'

def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    # Security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    if IS_PRODUCTION:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; img-src 'self' data: https://*.tile.openstreetmap.org; connect-src 'self'"
    
    return response

def protect_api():
    # Only protect /api routes
    if request.path.startswith('/api/'):
        # Allow health, login, register, and status
        public_paths = [
            '/api/health',
            '/api/status',
            '/api/auth/login',
            '/api/auth/register',
            '/api/public/sessions',
            '/api/upload',
            '/api/upload/chunk',
            '/api/upload/complete',
            '/api/device/ping',
            '/api/devices/token'
        ]
        if request.path in public_paths:
            return
            
        # Also allow shared and public session data
        if request.path.startswith('/api/shared/') or request.path.startswith('/api/public/'):
            return
        
        # Allow profile photo serving
        if request.path.endswith('/photo') and request.path.startswith('/api/users/') and request.method == 'GET':
            return
            
        # Also allow logout (it handles its own JWT if needed, or just clears cookies)
        if request.path == '/api/auth/logout':
            return

        try:
            # For some endpoints, JWT is optional (we handle check inside)
            optional_jwt_paths = [
                '/api/sessions/' # We'll check prefixes
            ]
            
            verify_jwt_in_request()
        except Exception:
            return jsonify({"error": "Authentication required"}), 401

def not_found(e):
    return jsonify({"error": "Not found"}), 404

def internal_error(e):
    if IS_PRODUCTION:
        return jsonify({"error": "Internal server error"}), 500
    return jsonify({"error": str(e)}), 500
