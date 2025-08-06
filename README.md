# k3-automation
Declarative approach to deploying proxmox VMs, installing k3s with metallb loadbalancer, nginx instead of traefik and rook-ceph using ansible-playbooks for my homelab.

## Ansible-playbooks

### Getting started

#### group_vars/all

Yaml files that declare variables used in playbooks.

#### inventory

Directory that contains files with information about hosts and what groups they belong to. Ansible playbook will be run against these hosts. This repo dynamically generates the inventory file based on the configuration.yml.

#### roles
* `<role_name>/tasks` - Starting point for role/playbooks
* `<role_name>/template/<path>/<file>/<generated_to>/<template_name>.<extension>.j2` - Templates used to dynamically generate files at runtime utilizing variable files

**Happy automating!**

## Deployment

### Prerequisites
1. Running instance of Proxmox
2. 

### Procedure
1. Create a copy of configuration.yml.template and fill it out.
2. Run  `proxmox_generate_token.py` to create the ansible user, token_id, and token_secret on your primary proxmox host. Copy the output into your configuration.yml.
3. `0100` will generate inventory file
