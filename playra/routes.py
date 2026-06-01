def includeme(config):
    config.add_static_view('static', 'static', cache_max_age=3600)
    config.add_route('home', '/')

    # Profile
    config.add_route("profile", "/api/v1/profile/{user_id}")

    # Admin
    config.add_route("admin_users", "/api/v1/admin/users")
    config.add_route("admin_user_role", "/api/v1/admin/users/{user_id}/role")

    # Games
    config.add_route("games", "/api/v1/games")
    config.add_route("games_popular", "/api/v1/games/popular")
    config.add_route("games_recent", "/api/v1/games/recent")
    config.add_route("game", "/api/v1/games/{id}")
    config.add_route("game_user", "/api/v1/games/{id}/user")
    config.add_route("game_screenshots", "/api/v1/games/{id}/screenshots")
    config.add_route("game_series", "/api/v1/games/{id}/game-series")

    # Lists
    config.add_route("lists", "/api/v1/lists")
    config.add_route("lists_public", "/api/v1/lists/public")
    config.add_route("list", "/api/v1/lists/{id}")
    config.add_route("list_games", "/api/v1/lists/{id}/games")
