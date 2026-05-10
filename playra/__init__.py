from pyramid.config import Configurator

from playra.auth.authentication import SupabaseAuthenticationPolicy
from playra.auth.authorization import SupabaseAuthorizationPolicy
from playra.clients.rawg import get_rawg_client
from playra.clients.supabase import get_supabase_client


def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    with Configurator(settings=settings) as config:
        config.include('pyramid_jinja2')
        config.include('.routes')
        config.include('.models')
        config.scan()

        config.set_authentication_policy(SupabaseAuthenticationPolicy())
        config.set_authorization_policy(SupabaseAuthorizationPolicy())

        supabase_client = get_supabase_client()
        config.registry.supabase_client = supabase_client

        rawg_client = get_rawg_client()
        config.registry.rawg_client = rawg_client

    return config.make_wsgi_app()
