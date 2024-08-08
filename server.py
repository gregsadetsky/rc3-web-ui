from dotenv import load_dotenv

# call before any imports
load_dotenv()

import json
import os
import sqlite3
import time
import uuid

from flask import (
    Flask,
    Response,
    g,
    redirect,
    render_template,
    request,
    session,
    stream_with_context,
)

from utils.rc3_proxmox import list_all_containers
from utils.rc_api import get_user_profile
from utils.rc_oauth_utils import get_rc_oauth

DATABASE_PATH = os.environ["DATABASE_PATH"]


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE_PATH)
        db.row_factory = sqlite3.Row
        # create table if it does not exist of 'tasks' with:
        # id, input_payload, status and output_message
        db.execute(
            "CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, type TEXT, input_payload TEXT, status TEXT, output_message TEXT)"
        )
        # create table 'tmate'
        # with columns vmid, ssh connection string
        db.execute(
            "CREATE TABLE IF NOT EXISTS tmate (vmid INTEGER PRIMARY KEY, ssh_connection_string TEXT)"
        )

        db.commit()

    return db


app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


@app.route("/")
def index():
    return render_template("index.html")


def _augment_containers_with_tmate_connection_strings(all_containers):
    # augment containers by finding tmate connection strings
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM tmate")
    tmate_rows = cursor.fetchall()
    tmate_dict = {row["vmid"]: row["ssh_connection_string"] for row in tmate_rows}
    for container in all_containers:
        container["tmate_connection_string"] = tmate_dict.get(container["vmid"])


@app.route("/dashboard")
def dashboard():
    if session.get("rc_user") is None:
        return get_rc_oauth(app).authorize_redirect(os.environ["RC_OAUTH_REDIRECT_URI"])

    rc_user_id_tag = f"rc-{session['rc_user']['user']['id']}"
    all_containers = list_all_containers(filter_by_tag_string=rc_user_id_tag)
    _augment_containers_with_tmate_connection_strings(all_containers)

    return render_template(
        "dashboard.html",
        user=session["rc_user"]["user"],
        all_containers=all_containers,
    )


@app.route("/create_new_container", methods=["POST"])
def create_new_container():
    if session.get("rc_user") is None:
        return get_rc_oauth(app).authorize_redirect(os.environ["RC_OAUTH_REDIRECT_URI"])

    # insert new task
    task_type = "create_container"
    task_id = str(uuid.uuid4())
    input_payload = {
        "tag_string": f'rc-{session["rc_user"]["user"]["id"]}',
    }
    status = "pending"
    output_message = "Starting..."
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO tasks (id, type, input_payload, status, output_message) VALUES (?, ?, ?, ?, ?)",
        (task_id, task_type, json.dumps(input_payload), status, output_message),
    )
    db.commit()

    return redirect(f"/task_status/{task_id}")


@app.route("/task_status/<task_id>")
def task_status(task_id):
    if session.get("rc_user") is None:
        return get_rc_oauth(app).authorize_redirect(os.environ["RC_OAUTH_REDIRECT_URI"])

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
    task = cursor.fetchone()
    if task is None:
        return "Task not found", 404

    return render_template(
        "task_status.html",
        task_id=task_id,
        output_message=task["output_message"],
        task_done=task["status"] == "done",
    )


@app.route("/change_container_status", methods=["POST"])
def change_container_status():
    if session.get("rc_user") is None:
        return get_rc_oauth(app).authorize_redirect(os.environ["RC_OAUTH_REDIRECT_URI"])

    # get all containers for this user -- does this user own this container?
    rc_user_id_tag = f"rc-{session['rc_user']['user']['id']}"
    all_containers = list_all_containers(filter_by_tag_string=rc_user_id_tag)

    container_id = request.form.get("container_id")
    action = request.form.get("action")
    if container_id is None or action is None:
        return "Missing container_id or action", 400

    found_container = None
    for container in all_containers:
        if container["vmid"] == int(container_id):
            found_container = container
            break

    if found_container is None:
        return "You don't own this container", 403

    # insert new task
    if action not in ["start", "stop", "delete"]:
        return "Invalid action", 400

    action_to_task_type = {
        "start": "start_container",
        "stop": "stop_container",
        "delete": "delete_container",
    }
    task_type = action_to_task_type[action]
    task_id = str(uuid.uuid4())
    input_payload = {
        "vmid": container_id,
    }
    status = "pending"
    output_message = "Queuing task..."
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO tasks (id, type, input_payload, status, output_message) VALUES (?, ?, ?, ?, ?)",
        (task_id, task_type, json.dumps(input_payload), status, output_message),
    )
    db.commit()
    return redirect(f"/task_status/{task_id}")


@app.route("/oauth_redirect")
def oauth_redirect():
    rc_oauth = get_rc_oauth(app)
    try:
        token = rc_oauth.authorize_access_token()
    except:
        return 'could not log you in. <a href="/dashboard">try again?</a>'
    user = get_user_profile(token["access_token"])
    session["rc_user"] = {
        "token": token,
        "user": user,
    }
    return redirect("/dashboard")


@app.route("/logout")
def logout():
    session["rc_user"] = None
    return redirect("/")


@app.route("/faq")
def faq():
    return render_template("faq.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
