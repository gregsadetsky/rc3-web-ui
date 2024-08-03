import os

from authlib.integrations.flask_client import OAuth


def get_rc_oauth(flask_app):
    rc_oauth = OAuth(flask_app).register(
        "Recurse Center",
        api_base_url="https://www.recurse.com/api/v1/",
        authorize_url="https://www.recurse.com/oauth/authorize",
        access_token_url="https://www.recurse.com/oauth/token",
        client_id=os.environ["RC_OAUTH_APP_ID"],
        client_secret=os.environ["RC_OAUTH_APP_SECRET"],
    )
    assert rc_oauth is not None
    return rc_oauth
