from pyramid.config import Configurator

from .services.supabase.client import get_supabase_client


def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    with Configurator(settings=settings) as config:
        config.include('pyramid_jinja2')
        config.include('.routes')
        config.include('.models')
        config.scan()

        supabase_client = get_supabase_client()
        config.registry.supabase_client = supabase_client

    return config.make_wsgi_app()
