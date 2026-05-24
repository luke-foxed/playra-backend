import logging

from pyramid.authentication import CallbackAuthenticationPolicy

from playra.clients.supabase import get_supabase_client

log = logging.getLogger(__name__)


class SupabaseAuthenticationPolicy(CallbackAuthenticationPolicy):

    def __init__(self):
        self.callback = None # prevent override of 'CallbackAuthenticationPolicy' init
        self.supabase_client = get_supabase_client()

    def unauthenticated_userid(self, request):
        auth = request.headers.get("Authorization")

        if not auth or not auth.startswith("Bearer "):
            return None

        token = auth.split(" ", 1)[1]

        try:
            response = self.supabase_client.auth.get_user(token)
        except Exception as e:
            log.warning("Token validation failed: %s", e)
            request.auth_token_invalid = True
            return None

        if not response.user or response.user.id is None:
            return None

        request.user_role = (response.user.app_metadata or {}).get('role')
        return response.user.id