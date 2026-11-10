from pyramid.config import Configurator

from playra.auth.authentication import SupabaseAuthenticationPolicy
from playra.auth.authorization import SupabaseAuthorizationPolicy
from playra.clients.cache import CacheClient
from playra.clients.igdb import get_igdb_client
from playra.clients.supabase import get_supabase_client


def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    with Configurator(settings=settings) as config:
        config.include('pyramid_jinja2')
        config.include('.routes')
        config.add_tween('playra.cors.cors_tween_factory')
        # playra.scripts holds one-off CLI tools (not Pyramid views), some of
        # which import deps the app itself doesn't need (e.g. psycopg2) --
        # scanning them in would crash app boot over an unrelated import.
        config.scan(ignore=['playra.scripts'])

        config.set_authentication_policy(SupabaseAuthenticationPolicy())
        config.set_authorization_policy(SupabaseAuthorizationPolicy())

        supabase_client = get_supabase_client()
        config.registry.supabase_client = supabase_client

        cache_client = CacheClient(supabase_client)
        config.registry.cache_client = cache_client

        igdb_client = get_igdb_client(cache_client)
        config.registry.igdb_client = igdb_client

    return config.make_wsgi_app()
