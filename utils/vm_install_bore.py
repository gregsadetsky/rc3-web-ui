from dotenv import load_dotenv

# call before any imports
load_dotenv()

import io
import os
import re
import sqlite3
import uuid

from dotenv import load_dotenv
from fabric import Connection

# call before any imports
load_dotenv()

BORE_SECRET = os.environ["BORE_SECRET"]
DATABASE_PATH = os.environ["DATABASE_PATH"]


def install_bore(vmid):
    yield "Installing bore (this is a good thing)"

    c = Connection(
        # TODO unhardcode
        host="root@10.100.7.196",
        connect_kwargs={"password": os.environ["PROXMOX_PASSWORD"]},
    )
    pct_prefix = f"pct exec {vmid} --"

    c.run(
        f"{pct_prefix} wget https://github.com/ekzhang/bore/releases/download/v0.5.1/bore-v0.5.1-x86_64-unknown-linux-musl.tar.gz"
    )
    c.run(f"{pct_prefix} tar -xvf bore-v0.5.1-x86_64-unknown-linux-musl.tar.gz")
    c.run(f"{pct_prefix} mv bore /usr/local/bin")

    # find the highest bore port, +1 and use that
    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row
    cursor = db.cursor()

    cursor.execute("SELECT * FROM bore_ports")
    rows = cursor.fetchall()
    bore_ports = [int(row["port"]) for row in rows]
    bore_port = max(bore_ports) + 1 if bore_ports else 20000

    systemd_service = f"""[Unit]
Description=bore service
After=network.target
StartLimitIntervalSec=0
[Service]
Type=simple
Restart=always
RestartSec=1
User=root
ExecStart=/usr/local/bin/bore local --to 23.136.216.135 22 -s "{BORE_SECRET}" -p {bore_port}

[Install]
WantedBy=multi-user.target
"""

    # ssh write to /etc/systemd/system/bore.service
    # make file like object
    f = io.StringIO(systemd_service)
    pve_host_machine_file_path = f"/tmp/bore.service-{uuid.uuid4()}"
    c.put(f, remote=pve_host_machine_file_path)
    # then transfer file over to guest
    c.run(
        f"pct push {vmid} {pve_host_machine_file_path} /etc/systemd/system/bore.service"
    )
    # then delete the file from the host
    c.run(f"rm {pve_host_machine_file_path}")

    # and start the service
    c.run(f"{pct_prefix} systemctl enable bore")
    c.run(f"{pct_prefix} systemctl start bore")
    c.run(f"{pct_prefix} systemctl status bore")

    # insert or update bore port in db
    # table bore_ports, columns vmid and port
    cursor.execute("SELECT * FROM bore_ports WHERE vmid=?", (vmid,))
    rows = cursor.fetchall()
    if rows:
        # the same vmid can be re-used by different machines,
        # so update the row if it exists
        cursor.execute("UPDATE bore_ports SET port=? WHERE vmid=?", (bore_port, vmid))
    else:
        cursor.execute(
            "INSERT INTO bore_ports (vmid, port) VALUES (?, ?)", (vmid, bore_port)
        )
    db.commit()
    db.close()

    yield "done"


if __name__ == "__main__":
    for _ in install_bore(113):
        print(_)
