# RC3 Web UI!

a web UI for the RC3 aka RCCC aka Recurse Center Cloud Computing!

this is a way for folks from the [Recurse Center](https://www.recurse.com/) to provision virtual servers using the very awesome [Proxmox](https://www.proxmox.com/)!

<img width="400" alt="Screen Shot 2024-08-02 at 10 10 37 PM" src="https://github.com/user-attachments/assets/08a67e09-33ec-44ad-ba1b-67cf8773f54d">

## how to dev

- see [HOWTODEV-OAUTH](https://github.com/gregsadetsky/rctv/blob/main/docs/HOWTODEV-OAUTH.md) from the RCTV project for the steps
-- very tldr: start the server, start ngrok, have an oauth dev app pointing to ngrok, and have a recurse domain for the dev app as well
-- in prod, it's all the same: have an oauth prod app pointing to the server, and have a recurse domain for the prod app

- this is a flask app; make a python venv, activate it, install requirements, run it using `python server.py`

## authors

this is a project by Greg Sadetsky, Ian Fisher and Clint J Edwards
