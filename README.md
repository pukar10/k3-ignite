# k3-automation
Declarative approach to deploying proxmox VMs, installing k3s and rook-ceph using ansible-playbooks for a homelab


# Ansible-playbooks

## Getting started

### group_vars/all

Yaml files that declare variables used in playbooks.

### inventory

Directory that contains files with information about hosts and what groups they belong to. Ansible playbook will be run against these hosts.

### roles

* `<role_name>/tasks` - Starting point for playbooks
* `<role_name>/template/<path>/<file>/<generated_to>/<template_name>.<extension>.j2` - Templates used to dynamically generate files at runtime utilizing variable files

### Happy automating!