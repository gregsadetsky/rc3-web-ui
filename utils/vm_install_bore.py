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

    systemd_service = f"""[Unit]
Description=bore service
After=network.target
StartLimitIntervalSec=0
[Service]
Type=simple
Restart=always
RestartSec=1
User=root
ExecStart=/usr/local/bin/bore local --to 23.136.216.135 22 -s "{BORE_SECRET}" -p 0

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
    output = c.run(f"{pct_prefix} systemctl status bore")

    # capture port and insert it into db.....!!!!!!!!!
    # look for "listening at 23.136.216.135:20109" and extract the port
    found_port = None
    bore_output = output.stdout
    bore_output_lines = bore_output.split("\n")
    for line in bore_output_lines:
        if "listening at" in line:
            res = re.search(r"listening at .*:(\d+)$", line.strip())
            if res:
                found_port = res.group(1)

    if not found_port:
        yield "Failed to find port bore is listening on"
        return

    # insert or update bore port in db
    # table bore_ports, columns vmid and port
    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row
    cursor = db.cursor()
    cursor.execute("SELECT * FROM bore_ports WHERE vmid=?", (vmid,))
    rows = cursor.fetchall()
    if rows:
        cursor.execute("UPDATE bore_ports SET port=? WHERE vmid=?", (found_port, vmid))
    else:
        cursor.execute(
            "INSERT INTO bore_ports (vmid, port) VALUES (?, ?)", (vmid, found_port)
        )
    db.commit()
    db.close()

    yield "done"


if __name__ == "__main__":
    for _ in install_bore(113):
        print(_)
