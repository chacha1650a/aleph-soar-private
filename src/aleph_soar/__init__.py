"""Application factory for the shared scaffold."""

from flask import Flask


def create_app(test_config=None):
    app = Flask(__name__)
    if test_config is not None:
        app.config.update(test_config)

    from .web import blueprint

    app.register_blueprint(blueprint)
    return app
