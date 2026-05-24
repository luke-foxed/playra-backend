import json
from functools import wraps
import logging

from pyramid.response import Response


def require_role(*roles):
    def decorator(view_fn):
        @wraps(view_fn)
        def wrapper(request):
            user_role = getattr(request, 'user_role', None)

            logging.debug(f"User role: {user_role}, Required roles: {roles}")

            if user_role not in roles:
                return Response(
                    json.dumps({"error": "Forbidden"}),
                    content_type="application/json",
                    charset="utf-8",
                    status=403,
                )
            return view_fn(request)
        return wrapper
    return decorator
