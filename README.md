# k3-automation
Declarative approach to deploying proxmox VMs, installing k3s with metallb loadbalancer, nginx instead of traefik and rook-ceph using ansible-playbooks for my homelab.

## To Do
- [ ] Wrapper playbook to run all playbooks to deploy and bootstrap cluster

## Getting started

`group_vars/all/` - files that declare variables used in all playbooks.

`inventory/` - contains files with information about hosts and what groups they belong to. Ansible playbook will be run against these hosts. This repo dynamically generates the inventory file based on the configuration.yml in group_vars

`roles/` - reusable self contained tasks

## Deployment

1. Copy `configuration.yml.template` to `configuration.yml` and fill out.
2. `ansible-playbook 0100-generate_inventory.yml` - generates the inventory file. 
3. `ansible-playbook 0200-preconfigure_vms.yml` - configures the VMs before k3s is installed.
4. `ansible-playbook 0300-install_k3.yml` - Installs minimal K3 onto all the nodes and joins them.
5. `ansible-playbook 0310-setup_local_env.yml` - Pulls kubeconfig to localhost
