def cors_tween_factory(handler, registry):
    settings = registry.settings
    raw = settings.get('cors.origins', '')
    allowed = {o.strip() for o in raw.split(',') if o.strip()}

    def cors_tween(request):
        origin = request.headers.get('Origin', '')

        if request.method == 'OPTIONS':
            response = request.response
            response.status_int = 200
            if origin in allowed:
                response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            response.headers['Access-Control-Max-Age'] = '3600'
            return response

        response = handler(request)

        if origin in allowed:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'

        return response

    return cors_tween
