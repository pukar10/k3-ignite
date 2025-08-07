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


def prompt_password_twice(label="Password for ansible@pve"):
    while True:
        p1 = getpass(f"{label}: ")
        if len(p1) < 8:
            print("Password must be at least 8 characters.")
            continue
        p2 = getpass("Confirm password: ")
        if p1 != p2:
            print("Passwords do not match. Try again.")
            continue
        return p1


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
    for flag in ("--output-format json", "--format json"):
        rc, out = runner(f"{cmd_base} {flag}")
        if rc == 0:
            try:
                json.loads(out)
                return rc, out, True
            except Exception:
                return rc, out, False
    rc, out = runner(cmd_base)
    return rc, out, False


def ensure_user(user_principal, comment, runner, password=None):
    """
    Ensure user exists. If creating, optionally set password at creation time.
    Returns (created: bool, msg: str)
    """
    rc, out, used_json = prefer_json("pveum user list", runner)
    if rc != 0:
        raise RuntimeError(f"Failed to list users:\n{out}")

    exists = False
    if used_json:
        try:
            items = json.loads(out)
            for it in items:
                if it.get("userid") == user_principal:
                    exists = True
                    break
        except Exception:
            pass
    if not exists and not used_json:
        exists = user_principal in out

    if exists:
        return False, "exists"

    # Create user (with password if provided)
    cmd = f"pveum user add {shlex.quote(user_principal)} --comment {shlex.quote(comment)}"
    if password:
        cmd += f" --password {shlex.quote(password)}"
    rc, out = runner(cmd)
    if rc != 0 and "already exists" not in out.lower():
        raise RuntimeError(f"Failed to create user:\n{out}")
    return True, out


def set_user_password(user_principal, password, runner):
    """
    Try multiple CLI variants to set/reset password for an existing user.
    """
    attempts = [
        f"pveum user modify {shlex.quote(user_principal)} --password {shlex.quote(password)}",
        f"pveum passwd {shlex.quote(user_principal)} --password {shlex.quote(password)}",
    ]
    last_out = ""
    for cmd in attempts:
        rc, out = runner(cmd)
        if rc == 0:
            return
        last_out = out
    raise RuntimeError(f"Failed to set password for {user_principal}.\nLast output:\n{last_out}")


def create_token(user_principal, token_name, privsep, runner):
    base = f"pveum user token add {shlex.quote(user_principal)} {shlex.quote(token_name)} --privsep {1 if privsep else 0}"
    rc, out, used_json = prefer_json(base, runner)
    if rc != 0:
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
            if isinstance(data, dict):
                secret = data.get("value") or data.get("secret")
            elif isinstance(data, list) and data:
                secret = data[0].get("value") or data[0].get("secret")
        except Exception:
            pass
    if secret is None:
        m = re.search(r"(?:value|Token value)\s*:\s*([A-Za-z0-9\.\-_]+)", out)
        if m:
            secret = m.group(1)

    if not secret:
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
    use_ssh = True

    runner = None
    ssh = None
    api_host_for_ansible = None

    if use_ssh:
        if paramiko is None:
            print("paramiko is required for SSH. Install with: pip install paramiko", file=sys.stderr)
            sys.exit(1)
        host = input("Proxmox host (FQDN/IP): ").strip()
        port = 22
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
        api_host_for_ansible = host
    else:
        runner = lambda cmd: run_local(cmd)
        api_host_for_ansible = input("Ansible proxmox.api_host (FQDN/IP for later) [this node's hostname/IP]: ").strip() or "pve"

    print("\n--- Proxmox User/Token Details ---")
    user_principal = "ansible@pve"
    token_name = "ansible"
    privsep = True
    role = "PVEAdmin"
    acl_paths = "/"
    acl_paths = [p.strip() for p in acl_paths.split(",") if p.strip()]

    # NEW: prompt for a password (twice) up front
    print("\n--- Password for ansible@pve ---")
    chosen_password = prompt_password_twice("Create password")

    print("\n--- Creating/Verifying User ---")
    try:
        created, msg = ensure_user(
            user_principal,
            "Automation user (created by script)",
            runner,
            password=chosen_password  # pass during creation when possible
        )
        if created:
            print(f"User created: {user_principal}")
        else:
            print(f"User exists: {user_principal}")
            if prompt_bool("Reset the user's password to the one you just entered?", False):
                set_user_password(user_principal, chosen_password, runner)
                print("Password updated.")
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
            principal = full_tokenid
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
