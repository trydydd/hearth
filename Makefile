# Makefile — CafeBox developer shortcuts
#
# Prerequisites:
#   vagrant                                          — for vm-* targets
#   scripts/config.py + scripts/generate-configs.py — for generate-configs
#   install.sh                                       — for the install target

.PHONY: help vm-start vm-stop vm-ssh vm-destroy install logs generate-configs _require-vagrant

# Default target: print help
help:
	@echo "CafeBox developer shortcuts"
	@echo ""
	@echo "  make vm-start         Start the development VM (vagrant up)"
	@echo "  make vm-stop          Stop the development VM (vagrant halt)"
	@echo "  make vm-ssh           Open an SSH session into the development VM"
	@echo "  make vm-destroy       Destroy the development VM (vagrant destroy -f)"
	@echo "  make install          Run install.sh inside the VM (or locally)"
	@echo "  make logs             Tail journald logs for all cafebox services"
	@echo "  make generate-configs Render all Jinja2 templates from cafe.yaml"

vm-start: _require-vagrant
	vagrant up

vm-stop: _require-vagrant
	vagrant halt

vm-ssh: _require-vagrant
	vagrant ssh

vm-destroy: _require-vagrant
	vagrant destroy -f

install:
	@test -f install.sh || { echo "ERROR: install.sh not found."; exit 1; }
	bash install.sh

logs: _require-vagrant
	vagrant ssh -c "journalctl -f -u 'cafebox-*'"

generate-configs:
	@test -f scripts/generate-configs.py || { echo "ERROR: scripts/generate-configs.py not found."; exit 1; }
	python scripts/generate-configs.py

_require-vagrant:
	@command -v vagrant >/dev/null 2>&1 || { echo "ERROR: vagrant is not installed. See https://developer.hashicorp.com/vagrant/downloads"; exit 1; }
