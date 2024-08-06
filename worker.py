from dotenv import load_dotenv

# call before any imports
load_dotenv()

import json
import os
import sqlite3
import time

from utils.rc3_proxmox import (
    create_container,
    delete_container,
    start_container,
    stop_container,
)

DATABASE_PATH = os.environ["DATABASE_PATH"]

TASK_NAME_TO_PROXMOXFN = {
    "create_container": create_container,
    "stop_container": stop_container,
    "start_container": start_container,
    "delete_container": delete_container,
}


def call_proxmox_task_yield_messages(fn, db, task_id, input_payload):
    try:
        for message in fn(
            **input_payload,
        ):
            print("Message:", message)
            # update task in database
            db.execute(
                "UPDATE tasks SET output_message=? WHERE id=?",
                (message, task_id),
            )
            db.commit()
    except Exception as e:
        print("ERR!!", e)
        db.execute(
            "UPDATE tasks SET status='done', output_message=? WHERE id=?",
            (f"ERRROR!! {e}", task_id),
        )
        db.commit()


def main():
    while True:
        # read from 'tasks' table
        # select all tasks with status 'pending'
        # and process them
        db = sqlite3.connect(DATABASE_PATH)
        db.row_factory = sqlite3.Row
        cursor = db.cursor()
        try:
            cursor.execute("SELECT * FROM tasks WHERE status='pending' LIMIT 1")
        except sqlite3.OperationalError as e:
            print("sqlite ERR!!", e)
            time.sleep(1)
            continue
        task = cursor.fetchone()
        if task is None:
            print("No tasks to process")
            time.sleep(1)
            continue

        print("Processing task", dict(task))

        if task["type"] not in TASK_NAME_TO_PROXMOXFN:
            print("ERR unknown task type!!", task)
            time.sleep(1)
            continue

        call_proxmox_task_yield_messages(
            TASK_NAME_TO_PROXMOXFN[task["type"]],
            db,
            task["id"],
            json.loads(task["input_payload"]),
        )

        # set status to done
        db.execute(
            "UPDATE tasks SET status='done' WHERE id=?",
            (task["id"],),
        )
        db.commit()


if __name__ == "__main__":
    # main()
    while True:
        print("worker running")
        time.sleep(5)
