#!/usr/bin/env python3
import json
import re
import shlex
import subprocess
import sys
from getpass import getpass

# Optional SSH support
try:
    import paramiko  # pip install paramiko
except ImportError:
    paramiko = None


def prompt_bool(q, default=True):
    d = "Y/n" if default else "y/N"
    while True:
        ans = input(f"{q} [{d}]: ").strip().lower()
        if ans == "" and default is not None:
            return default
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("Please answer y or n.")


def run_local(cmd):
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return res.returncode, res.stdout


def run_ssh(ssh, cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode() + stderr.read().decode()
    rc = stdout.channel.recv_exit_status()
    return rc, out


def prefer_json(cmd_base, runner):
    """
    Try pveum with JSON flags, fall back to plain output.
    Returns (rc, stdout, used_json)
    """
    # Newer tools: --output-format json ; some older accept --format json
    for flag in ("--output-format json", "--format json"):
        rc, out = runner(f"{cmd_base} {flag}")
        if rc == 0:
            try:
                json.loads(out)
                return rc, out, True
            except Exception:
                # was successful but not json; keep as plain
                return rc, out, False
    # Fall back to plain
    rc, out = runner(cmd_base)
    return rc, out, False


def ensure_user(user_principal, comment, runner):
    # Check if user exists
    # Try JSON first
    rc, out, used_json = prefer_json("pveum user list", runner)
    if rc != 0:
        raise RuntimeError(f"Failed to list users:\n{out}")
    exists = False
    if used_json:
        try:
            items = json.loads(out)
            # pveum user list JSON may be array of dicts with 'userid'
            for it in items:
                if it.get("userid") == user_principal:
                    exists = True
                    break
        except Exception:
            pass
    if not exists and not used_json:
        # Grep fallback
        exists = user_principal in out

    if exists:
        return False, "exists"
    # Create user
    cmd = f"pveum user add {shlex.quote(user_principal)} --comment {shlex.quote(comment)}"
    rc, out = runner(cmd)
    if rc != 0 and "already exists" not in out.lower():
        raise RuntimeError(f"Failed to create user:\n{out}")
    return True, out


def create_token(user_principal, token_name, privsep, runner):
    # Try to create token and parse secret from JSON
    base = f"pveum user token add {shlex.quote(user_principal)} {shlex.quote(token_name)} --privsep {1 if privsep else 0}"
    rc, out, used_json = prefer_json(base, runner)
    if rc != 0:
        # If token exists, we need to detect it (but secret won't be retrievable)
        if "already exists" in out.lower():
            raise RuntimeError(
                "Token already exists and Proxmox will not re-show the secret.\n"
                "Delete it (pveum user token delete ...) or choose a new token name."
            )
        raise RuntimeError(f"Failed to create token:\n{out}")

    tokenid = f"{user_principal}!{token_name}"
    secret = None
    if used_json:
        try:
            data = json.loads(out)
            # Proxmox prints a single dict with fields like 'full-tokenid' and 'value' (secret)
            if isinstance(data, dict):
                secret = data.get("value") or data.get("secret")
            elif isinstance(data, list) and data:
                # some versions return a list with one item
                secret = data[0].get("value") or data[0].get("secret")
        except Exception:
            pass
    if secret is None:
        # Fallback regex search
        # look for 'value: <secret>' or 'Token value: <secret>'
        m = re.search(r"(?:value|Token value)\s*:\s*([A-Za-z0-9\.\-_]+)", out)
        if m:
            secret = m.group(1)

    if not secret:
        # Last resort: print output so user can see it and copy/paste manually
        raise RuntimeError(
            "Token created but could not detect the secret automatically.\n"
            f"Raw output was:\n{out}\n"
            "Please capture the secret now; Proxmox shows it only once."
        )

    return tokenid, secret


def assign_acl(path, principal, role, runner, is_token=False):
    if is_token:
        cmd = f"pveum aclmod {shlex.quote(path)} -token {shlex.quote(principal)} -role {shlex.quote(role)}"
    else:
        cmd = f"pveum aclmod {shlex.quote(path)} -user {shlex.quote(principal)} -role {shlex.quote(role)}"
    rc, out = runner(cmd)
    if rc != 0:
        raise RuntimeError(f"Failed to assign ACL on {path}:\n{out}")


def main():
    print("=== Proxmox API Token Bootstrap ===")
    #use_ssh = prompt_bool("Connect over SSH to a Proxmox node?", True)
    use_ssh = True

    runner = None
    ssh = None
    api_host_for_ansible = None

    if use_ssh:
        if paramiko is None:
            print("paramiko is required for SSH. Install with: pip install paramiko", file=sys.stderr)
            sys.exit(1)
        host = input("Proxmox host (FQDN/IP): ").strip()
        #port_in = input("SSH port [22]: ").strip()
        #port = int(port_in) if port_in else 22
        port = 22
        #user = input("SSH user [root]: ").strip() or "root"
        user = "root"

        auth_method_key = prompt_bool("Use SSH key authentication?", True)
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            if auth_method_key:
                key_path = input("Private key path [~/.ssh/id_rsa or id_ed25519]: ").strip() or None
                if key_path:
                    pkey = paramiko.RSAKey.from_private_key_file(key_path)
                    ssh_client.connect(host, port=port, username=user, pkey=pkey, timeout=15)
                else:
                    ssh_client.connect(host, port=port, username=user, timeout=15)
            else:
                pw = getpass("SSH password: ")
                ssh_client.connect(host, port=port, username=user, password=pw, timeout=15)
        except Exception as e:
            print(f"SSH connection failed: {e}", file=sys.stderr)
            sys.exit(1)

        ssh = ssh_client
        runner = lambda cmd: run_ssh(ssh, cmd)
        api_host_for_ansible = host  # good default: same host for Ansible api_host
    else:
        # local run (execute on a Proxmox node directly)
        runner = lambda cmd: run_local(cmd)
        api_host_for_ansible = input("Ansible proxmox.api_host (FQDN/IP for later) [this node's hostname/IP]: ").strip() or "pve"

    # Collect Proxmox objects to create
    print("\n--- Proxmox User/Token Details ---")
    #realm = input("Realm [pve]: ").strip() or "pve"
    #username = input("Automation username [ansible]: ").strip() or "ansible"
    #user_principal = f"{username}@{realm}"
    user_principal = "ansible@pve"

    #token_name = input("Token name [ansible]: ").strip() or "ansible"
    token_name = "ansible"
    #privsep = prompt_bool("Enable privilege separation for token?", True)
    privsep = True
    #role = input("Role to grant [PVEAdmin]: ").strip() or "PVEAdmin"
    role = "PVEAdmin"
    #acl_paths = input("ACL path(s), comma-separated [/]: ").strip() or "/"
    acl_paths = "/"
    acl_paths = [p.strip() for p in acl_paths.split(",") if p.strip()]

    print("\n--- Creating/Verifying User ---")
    try:
        created, msg = ensure_user(user_principal, "Automation user (created by script)", runner)
        if created:
            print(f"User created: {user_principal}")
        else:
            print(f"User exists: {user_principal}")
    except Exception as e:
        print(str(e), file=sys.stderr)
        if ssh:
            ssh.close()
        sys.exit(1)

    print("\n--- Creating Token ---")
    try:
        full_tokenid, secret = create_token(user_principal, token_name, privsep, runner)
        print(f"Token created: {full_tokenid}")
        print("SECRET (copy and store securely; shown only once):")
        print(secret)
    except Exception as e:
        print(str(e), file=sys.stderr)
        if ssh:
            ssh.close()
        sys.exit(1)

    print("\n--- Assigning ACL(s) ---")
    try:
        if privsep:
            principal = full_tokenid  # token principal
            for p in acl_paths:
                assign_acl(p, principal, role, runner, is_token=True)
        else:
            principal = user_principal
            for p in acl_paths:
                assign_acl(p, principal, role, runner, is_token=False)
        print(f"ACL(s) applied to {principal} on {', '.join(acl_paths)} with role {role}")
    except Exception as e:
        print(str(e), file=sys.stderr)
        if ssh:
            ssh.close()
        sys.exit(1)

    if ssh:
        ssh.close()

    print("\n--- Ansible vars (example) ---")
    print("Add this to your group_vars/all/configuration.yaml (vault the secret):\n")
    print("proxmox:")
    print(f"  api_host: \"{api_host_for_ansible}\"")
    print(f"  api_user: \"{user_principal}\"")
    print(f"  api_token_id: \"{full_tokenid}\"")
    print(f"  api_token_secret: \"{secret}\"  # ← vault this")
    print("  validate_certs: false")


if __name__ == "__main__":
    main()
