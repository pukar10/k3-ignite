#!/usr/bin/env python3
import sys
import urllib3
from getpass import getpass
from datetime import datetime
from proxmoxer import ProxmoxAPI

# ===== Edit these if needed =====
PROXMOX_HOST    = "192.168.1.30"  # Hostname or IP of a Proxmox node or cluster VIP
ADMIN_USER      = "root@pam"      # Existing admin to authenticate the API call
REALM           = "pve"           # "pve" (local auth) or "pam" (system auth) for the new user
NEW_USER        = "ansible"       # The user we create/manage
TOKEN_BASENAME  = "ansible"     # Preferred token id (will auto-unique if already used)
ROLE            = "Administrator" # Full access
VERIFY_SSL      = False           # Set True if your Proxmox has a valid certificate

# (Quiet self-signed cert warnings if VERIFY_SSL is False)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def prompt_password_twice(label: str, min_len: int = 12) -> str:
    while True:
        p1 = getpass(f"{label}: ")
        p2 = getpass("Confirm password: ")
        if p1 != p2:
            print("Passwords do not match. Try again.")
            continue
        return p1

def unique_token_id(preferred: str, existing_ids: set) -> str:
    """Return preferred if free; otherwise append a timestamp suffix."""
    if preferred not in existing_ids:
        return preferred
    return f"{preferred}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

def main():
    # --- Prompt for credentials (not echoed) ---
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
        has_admin = any(
            a.get("userid") == user_id and a.get("roleid") == ROLE and a.get("path") == "/"
            for a in acls
        )
        if has_admin:
            print(f"ℹ️ '{user_id}' already has '{ROLE}' on '/'.")
        else:
            print(f"✅ Granting '{ROLE}' to '{user_id}' on '/'")
            proxmox.access.acl.put(path="/", users=user_id, roles=ROLE)
    except Exception as e:
        print(f"❌ Error assigning role: {e}")
        sys.exit(1)

    # --- Create API token (no privilege separation; inherits user's perms) ---
    try:
        # Collect existing token IDs to avoid conflicts
        existing_tokens = proxmox.access.users(user_id).token.get()  # list of dicts
        existing_ids = {t.get("tokenid") for t in existing_tokens} if isinstance(existing_tokens, list) else set()
        token_id = unique_token_id(TOKEN_BASENAME, existing_ids)

        print(f"✅ Creating API token '{token_id}' for '{user_id}'")
        # privsep=0 => token inherits user's privileges (full in this case)
        resp = proxmox.access.users(user_id).token(token_id).post(comment="Ansible automation token", privsep=0)

        # API returns the secret only once at creation time
        token_secret = resp.get("value")
        if not token_secret:
            raise RuntimeError("API did not return token secret (value). Token may already exist.")
    except Exception as e:
        print(f"❌ Error creating API token: {e}")
        sys.exit(1)

    full_token_id = f"{user_id}!{token_id}"

    # --- Print ready-to-paste YAML for your Ansible vars ---
    print("\n# === Save these in your Ansible vars ===")
    print(f'api_host: "{PROXMOX_HOST}"')
    print(f'api_user: "{user_id}"')
    print(f'api_user_password: "{new_user_pass}"')
    print(f'api_token_id: "{full_token_id}"')
    print(f'api_token_secret: "{token_secret}"')
    print("\n🎉 Done. User and API token are ready.")

if __name__ == "__main__":
    main()
