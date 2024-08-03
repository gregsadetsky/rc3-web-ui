import requests


def try_to_get_ssh_keys_from_github_for_rc_user(rc_user_object):
    github_username = rc_user_object.get("github")
    if not github_username:
        return []

    # fetch keys from github
    r = requests.get(f"https://api.github.com/users/{github_username}/keys")
    if not r.ok:
        return []

    return [key["key"].strip() for key in r.json()]
