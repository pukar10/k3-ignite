#!/usr/bin/env python3
import sys
import urllib3
from getpass import getpass
from proxmoxer import ProxmoxAPI

# ===== Config (edit as needed) =====
PROXMOX_HOST = "192.168.1.30"   # Proxmox node or VIP
ADMIN_USER   = "root@pam"       # Must be an existing admin
REALM        = "pve"            # "pve" for local auth, "pam" for system auth
NEW_USER     = "ansible"        # User to create
ROLE         = "Administrator"  # Full access role
VERIFY_SSL   = False            # Set True if you have a valid cert

# ===== Optional: quiet self-signed cert warnings =====
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def prompt_password_twice(label: str) -> str:
    while True:
        p1 = getpass(f"{label}: ")
        p2 = getpass("Confirm password: ")
        if p1 != p2:
            print("Passwords do not match. Try again.")
            continue
        return p1

def main():
    # --- Prompt for passwords (not echoed) ---
    admin_pass = getpass(f"Password for {ADMIN_USER}: ")
    new_user_pass = prompt_password_twice(f"New password for {NEW_USER}@{REALM}")

    # --- Connect ---
    try:
        proxmox = ProxmoxAPI(
            PROXMOX_HOST,
            user=ADMIN_USER,
            password=admin_pass,
            verify_ssl=VERIFY_SSL,
        )
    except Exception as e:
        print(f"❌ Failed to connect to Proxmox API at {PROXMOX_HOST}: {e}")
        sys.exit(1)

    user_id = f"{NEW_USER}@{REALM}"

    # --- Ensure user exists ---
    try:
        users = proxmox.access.users.get()
        if any(u.get("userid") == user_id for u in users):
            print(f"ℹ️ User '{user_id}' already exists. Skipping creation.")
        else:
            print(f"✅ Creating user '{user_id}'")
            proxmox.access.users.post(userid=user_id, password=new_user_pass, comment="Ansible automation user")
    except Exception as e:
        print(f"❌ Error ensuring user exists: {e}")
        sys.exit(1)

    # --- Ensure Administrator role on '/' ---
    try:
        acls = proxmox.access.acl.get()
        already_has_admin = any(
            a.get("userid") == user_id and a.get("roleid") == ROLE and a.get("path") == "/"
            for a in acls
        )
        if already_has_admin:
            print(f"ℹ️ '{user_id}' already has '{ROLE}' on '/'.")
        else:
            print(f"✅ Granting '{ROLE}' to '{user_id}' on '/'")
            proxmox.access.acl.put(path="/", users=user_id, roles=ROLE)
    except Exception as e:
        print(f"❌ Error assigning role: {e}")
        sys.exit(1)

    print("🎉 Done. The Ansible user has full access.")

if __name__ == "__main__":
    main()
