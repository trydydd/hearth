# Makefile — CafeBox developer shortcuts
#
# Prerequisites:
#   vagrant          — for vm-* targets (https://www.vagrantup.com)
#   ansible-playbook — for install / vm-provision targets (https://www.ansible.com)
#   scripts/config.py + scripts/generate-configs.py — for generate-configs

.PHONY: help vm-start vm-stop vm-ssh vm-provision install logs generate-configs

# Default target: print help
help:
	@echo "CafeBox developer shortcuts"
	@echo ""
	@echo "  make vm-start         Start the Vagrant dev VM (Debian 13 trixie)"
	@echo "  make vm-stop          Stop the Vagrant dev VM"
	@echo "  make vm-ssh           Open an SSH session into the dev VM"
	@echo "  make vm-provision     Re-run Ansible provisioning inside the dev VM"
	@echo "  make install          Run Ansible playbook (provision VM or local host)"
	@echo "  make logs             Tail journald logs for all cafebox services"
	@echo "  make generate-configs Render all Jinja2 templates from cafe.yaml"

vm-start:
	@command -v vagrant >/dev/null 2>&1 || { echo "ERROR: vagrant is not installed. See README.md."; exit 1; }
	vagrant up

vm-stop:
	@command -v vagrant >/dev/null 2>&1 || { echo "ERROR: vagrant is not installed. See README.md."; exit 1; }
	vagrant halt

vm-ssh:
	@command -v vagrant >/dev/null 2>&1 || { echo "ERROR: vagrant is not installed. See README.md."; exit 1; }
	vagrant ssh

vm-provision:
	@command -v vagrant >/dev/null 2>&1 || { echo "ERROR: vagrant is not installed. See README.md."; exit 1; }
	vagrant provision

install:
	@command -v ansible-playbook >/dev/null 2>&1 || { echo "ERROR: ansible-playbook is not installed. See README.md."; exit 1; }
	@test -f ansible/playbook.yml || { echo "ERROR: ansible/playbook.yml not found."; exit 1; }
	ansible-playbook ansible/playbook.yml -i ansible/inventory.yml

logs:
	@command -v vagrant >/dev/null 2>&1 || { echo "ERROR: vagrant is not installed. See README.md."; exit 1; }
	vagrant ssh -c "journalctl -f -u 'cafebox-*'"

generate-configs:
	@test -f scripts/generate-configs.py || { echo "ERROR: scripts/generate-configs.py not found."; exit 1; }
	python scripts/generate-configs.py
