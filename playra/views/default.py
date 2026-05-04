from pyramid.response import Response
from pyramid.view import view_config


@view_config(route_name="home", renderer="json", permission="authenticated")
def my_view(request):
    try:
        supabase_client = request.registry.supabase_client
        response = supabase_client.from_("test").select("*").execute()

        return {"data": response.data}

    except Exception as e:
        return Response(
            f"An error occurred while fetching data: {str(e)}",
            content_type="text/plain",
            status=500,
        )
