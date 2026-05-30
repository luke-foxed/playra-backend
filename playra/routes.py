def includeme(config):
    config.add_static_view('static', 'static', cache_max_age=3600)
    config.add_route('home', '/')

    # Profile
    config.add_route("profile", "/api/v1/profile/{user_id}")

    # Games
    config.add_route("games", "/api/v1/games")
    config.add_route("game", "/api/v1/games/{id}")
    config.add_route("game_user", "/api/v1/games/{id}/user")

    # Lists
    config.add_route("lists", "/api/v1/lists")
    config.add_route("list", "/api/v1/lists/{id}")
    config.add_route("list_games", "/api/v1/lists/{id}/games")
