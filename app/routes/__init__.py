def register_routes(flask_app):
    from app.routes.health import health_bp
    flask_app.register_blueprint(health_bp)
