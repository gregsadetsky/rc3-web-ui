from dotenv import load_dotenv

# call before any imports
load_dotenv()

import os
import sys
import time
import warnings
from pathlib import Path

from proxmoxer import ProxmoxAPI

"""
Authentication?

- this uses root Proxmox password -- obviously this is bad
- using any kind of hard-coded credential won't work because we need to distribute
- so user has to supply some credential
"""

# suppressing warnings from `verify_ssl=False` below
warnings.filterwarnings("ignore", module="urllib3.connectionpool")
proxmox = ProxmoxAPI(
    "10.100.7.196:8006",
    user="root@pam",
    password=os.environ["PROXMOX_PASSWORD"],
    verify_ssl=False,
)


def list_all_containers(filter_by_tag_string):
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
    max_vmid = 100
    for node in proxmox.nodes("pve").lxc().get():
        max_vmid = max(node["vmid"], max_vmid)

    return max_vmid + 1


def create_container(ssh_public_keys, tag_string):
    # sshpub, sshpriv = normalize_ssh(sshfile)
    # ssh_public_keys = Path(sshpub).read_text()
    invalid_keywords = {"ssh-public-keys": ssh_public_keys}
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
        **invalid_keywords,
    )
    yield (f"Creating server #{vmid}. (This may take like 10 seconds.)")

    while True:
        task_status = proxmox.nodes("pve").tasks(task_id).status.get()
        if task_status["status"] == "stopped":
            yield (f"Finished creating server #{vmid}.")
            break
        time.sleep(1.0)

    # re-use function that we will call from the ui when starting
    # existing container
    # SORRY FOR THE UGLY PYTHON
    for _ in start_container(vmid):
        yield _

    # print()
    # print("Log in:")
    # print(f"  $ ssh -i {sshpriv} root@{ip_addr}")
    # print()
    # print("Have a nice day.")


def start_container(vmid):
    proxmox.nodes("pve").lxc(vmid).status.start.post()
    yield (f"Waiting for server #{vmid} to start.")
    while True:
        lxc_status = proxmox.nodes("pve").lxc(vmid).status.current.get()
        if lxc_status["status"] == "running":
            yield (f"Server #{vmid} has started.")
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
        yield ("Unable to fetch server's IP address. Check the admin interface?")
        return


def delete_container(vmid):
    proxmox.nodes("pve").lxc(vmid).delete()
    yield (f"Deleting server #{vmid}.")
    while True:
        all_containers = proxmox.nodes("pve").lxc().get()
        if vmid not in [container["vmid"] for container in all_containers]:
            yield (f"Server #{vmid} has been deleted.")
            break
        time.sleep(0.5)


def stop_container(vmid):
    proxmox.nodes("pve").lxc(vmid).status.stop.post()
    yield (f"Stopping server #{vmid}.")
    while True:
        lxc_status = proxmox.nodes("pve").lxc(vmid).status.current.get()
        if lxc_status["status"] == "stopped":
            yield (f"Server #{vmid} has stopped.")
            break
        time.sleep(0.5)

    yield (f"Server #{vmid} has been stopped.")


def get_ip_addr(vmid):
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


# create_container(sys.argv[1])
# print(get_ip_addr(102))
