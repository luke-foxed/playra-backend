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
        response = self.supabase_client.auth.get_user(token)

        if response.user.id is None:
            return None

        return response.user.id