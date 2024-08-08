from dotenv import load_dotenv

# call before any imports
load_dotenv()

import os
import sqlite3
import sys
import time
import uuid
import warnings
from pathlib import Path

from proxmoxer import ProxmoxAPI

from .vm_install_tmate import install_tmate

DATABASE_PATH = os.environ["DATABASE_PATH"]

"""
Authentication?

- this uses root Proxmox password -- obviously this is bad
- using any kind of hard-coded credential won't work because we need to distribute
- so user has to supply some credential
"""

# suppressing warnings from `verify_ssl=False` below
warnings.filterwarnings("ignore", module="urllib3.connectionpool")


def get_proxmox():
    # "ProxmoxAPI" uses a token that expires after 2 hours!!!!
    # for the time being, re-create connection on every function call.
    # a better strategy would be to recreate it only if it's older than 1 hour
    # (default timeout is 2 hours).
    # I did try to use an api token (which proxmox is supposed to support)
    # but I could not connect using the token -- was getting weird errors about the username
    # being "root@pam!root@pam"...
    return ProxmoxAPI(
        # TODO unhardcode
        "10.100.7.196:8006",
        user="root@pam",
        password=os.environ["PROXMOX_PASSWORD"],
        verify_ssl=False,
    )


def list_all_containers(filter_by_tag_string):
    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row
    cursor = db.cursor()

    proxmox = get_proxmox()
    # let's get all the containers and augment them by
    # getting each one's IP address
    all_containers = proxmox.nodes("pve").lxc().get()
    all_containers = filter(
        lambda container: filter_by_tag_string == container.get("tags"), all_containers
    )
    all_containers = list(all_containers)
    for container in all_containers:
        container["ip_addr"] = get_ip_addr(container["vmid"])
    # sort by vmid
    return list(sorted(all_containers, key=lambda container: container["vmid"]))


def get_next_vmid():
    proxmox = get_proxmox()
    max_vmid = 100
    for node in proxmox.nodes("pve").lxc().get():
        max_vmid = max(node["vmid"], max_vmid)

    return max_vmid + 1


def create_container(tag_string):
    proxmox = get_proxmox()
    vmid = get_next_vmid()
    task_id = proxmox.nodes("pve").lxc.post(
        node="pve",
        # TODO: how to figure out?
        ostemplate="local:vztmpl/ubuntu-23.10-standard_23.10-1_amd64.tar.zst",
        vmid=vmid,
        features="nesting=1",
        # TODO: how to figure out?
        storage="local-lvm",
        net0="name=eth0,bridge=vmbr0,firewall=1,ip6=dhcp,ip=dhcp",
        rootfs="local-lvm:8",
        cores=1,
        memory=512,
        swap=512,
        unprivileged=1,
        tags=tag_string,
        # generate a throwaway secure enough password
        password=str(uuid.uuid4()),
    )
    yield (f"Creating machine #{vmid}. (This may take like 10 seconds.)")

    while True:
        task_status = proxmox.nodes("pve").tasks(task_id).status.get()
        if task_status["status"] == "stopped":
            yield (f"Finished creating machine #{vmid}.")
            break
        time.sleep(1.0)

    # re-use function that we will call from the ui when starting
    # existing container
    # SORRY FOR THE UGLY PYTHON
    for _ in start_container(vmid):
        yield _

    for _ in install_tmate(vmid):
        yield _


def start_container(vmid):
    proxmox = get_proxmox()
    proxmox.nodes("pve").lxc(vmid).status.start.post()
    yield (f"Waiting for machine #{vmid} to start.")
    while True:
        lxc_status = proxmox.nodes("pve").lxc(vmid).status.current.get()
        if lxc_status["status"] == "running":
            yield (f"Machine #{vmid} has started.")
            break
        time.sleep(0.5)

    yield ("Waiting for network connection.")
    ip_addr = None
    for _ in range(10):
        ip_addr = get_ip_addr(vmid)
        if ip_addr is not None:
            break
        time.sleep(1.0)

    if ip_addr is None:
        yield ("Unable to fetch machine's IP address. Check the admin interface?")
        return


def delete_container(vmid):
    proxmox = get_proxmox()
    proxmox.nodes("pve").lxc(vmid).delete()
    yield (f"Deleting machine #{vmid}.")
    while True:
        all_containers = proxmox.nodes("pve").lxc().get()
        if vmid not in [container["vmid"] for container in all_containers]:
            yield (f"Machine #{vmid} has been deleted.")
            break
        time.sleep(0.5)


def stop_container(vmid):
    proxmox = get_proxmox()
    proxmox.nodes("pve").lxc(vmid).status.stop.post()
    yield (f"Stopping machine #{vmid}.")
    while True:
        lxc_status = proxmox.nodes("pve").lxc(vmid).status.current.get()
        if lxc_status["status"] == "stopped":
            yield (f"Machine #{vmid} has stopped.")
            break
        time.sleep(0.5)

    yield (f"Machine #{vmid} has been stopped.")


def get_ip_addr(vmid):
    proxmox = get_proxmox()
    interfaces = proxmox.nodes("pve").lxc(vmid).interfaces.get()
    if interfaces is None:
        return None

    for interface in interfaces:
        if interface["name"] == "eth0" and "inet" in interface:
            return interface["inet"].split("/", maxsplit=1)[0]

    return None


# returns (public, private)
def normalize_ssh(sshfile):
    if sshfile.endswith(".pub"):
        return sshfile, sshfile[:-4]
    else:
        return sshfile + ".pub", sshfile
