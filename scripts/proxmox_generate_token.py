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
                secr
