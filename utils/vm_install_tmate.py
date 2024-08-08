from dotenv import load_dotenv

# call before any imports
load_dotenv()

import io
import os
import random
import re
import sqlite3
import string
import uuid

from dotenv import load_dotenv
from fabric import Connection

# call before any imports
load_dotenv()

TMATE_API_KEY = os.environ["TMATE_API_KEY"]
DATABASE_PATH = os.environ["DATABASE_PATH"]


def install_tmate(vmid):
    yield "Installing tmate (this is a good thing)"

    c = Connection(
        # TODO unhardcode
        host="root@10.100.7.196",
        connect_kwargs={"password": os.environ["PROXMOX_PASSWORD"]},
    )
    pct_prefix = f"pct exec {vmid} --"

    c.run(f"{pct_prefix} apt install -y tmate")

    # generate 25-char long random lowercase+uppercase+digits string
    tmate_client_string = "".join(
        random.choices(
            string.ascii_lowercase + string.ascii_uppercase + string.digits, k=25
        )
    )

    systemd_service = f"""[Unit]
Description=tmate service
After=network.target
StartLimitIntervalSec=0
[Service]
Type=simple
Restart=always
RestartSec=1
User=root
ExecStart=tmate -F -n {tmate_client_string} -k {TMATE_API_KEY}

[Install]
WantedBy=multi-user.target
"""

    # ssh write to /etc/systemd/system/tmate.service
    # make file like object
    f = io.StringIO(systemd_service)
    pve_host_machine_file_path = f"/tmp/tmate.service-{uuid.uuid4()}"
    c.put(f, remote=pve_host_machine_file_path)
    # then transfer file over to guest
    c.run(
        f"pct push {vmid} {pve_host_machine_file_path} /etc/systemd/system/tmate.service"
    )
    # then delete the file from the host
    c.run(f"rm {pve_host_machine_file_path}")

    # and start the service
    c.run(f"{pct_prefix} systemctl enable tmate")
    c.run(f"{pct_prefix} systemctl start tmate")
    status_output = c.run(f"{pct_prefix} systemctl status tmate")

    ssh_connection_string = None
    # find "ssh session: ssh rc3/..." string in the output, extract everything starting at rc3/
    for line in status_output.stdout.split("\n"):
        if "ssh session: ssh rc3/" in line:
            ssh_connection_string = re.search(r"ssh (rc3/.+)$", line).group(1)
            break

    assert ssh_connection_string, "Could not find ssh connection string"

    # insert or update ssh connection string in db
    # table tmate, columns vmid and port
    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row
    cursor = db.cursor()
    cursor.execute("SELECT * FROM tmate WHERE vmid=?", (vmid,))
    rows = cursor.fetchall()
    if rows:
        # the same vmid can be re-used by different machines,
        # so update the row if it exists
        cursor.execute(
            "UPDATE tmate SET ssh_connection_string=? WHERE vmid=?",
            (ssh_connection_string, vmid),
        )
    else:
        cursor.execute(
            "INSERT INTO tmate (vmid, ssh_connection_string) VALUES (?, ?)",
            (vmid, ssh_connection_string),
        )
    db.commit()
    db.close()

    yield "done"
