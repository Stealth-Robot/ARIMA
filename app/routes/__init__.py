def register_routes(flask_app):
    from app.routes.health import health_bp
    from app.routes.auth import auth_bp
    from app.routes.home import home_bp
    from app.routes.profile import profile_bp
    from app.routes.ratings import ratings_bp
    from app.routes.artists import artists_bp
    from app.routes.stats import stats_bp

    flask_app.register_blueprint(health_bp)
    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(home_bp)
    flask_app.register_blueprint(profile_bp)
    flask_app.register_blueprint(ratings_bp)
    flask_app.register_blueprint(artists_bp)
    flask_app.register_blueprint(stats_bp)
