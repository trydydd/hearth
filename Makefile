# Makefile — CafeBox developer shortcuts
#
# Prerequisites:
#   vagrant — for all vm-* and logs targets
#
# Note: install.sh and generate-configs.py are NOT invoked directly from here.
# Both are called automatically by `vagrant provision` (via the Vagrantfile shell
# provisioner), so running `make vm-start` is sufficient to get a fully-configured
# development VM.

.PHONY: help vm-start vm-stop vm-ssh vm-destroy logs _require-vagrant

# Default target: print help
help:
	@echo "CafeBox developer shortcuts"
	@echo ""
	@echo "  make vm-start   Start the development VM (vagrant up)"
	@echo "  make vm-stop    Stop the development VM (vagrant halt)"
	@echo "  make vm-ssh     Open an SSH session into the development VM"
	@echo "  make vm-destroy Destroy the development VM (vagrant destroy -f)"
	@echo "  make logs       Tail journald logs for all cafebox services"

vm-start: _require-vagrant
	vagrant up

vm-stop: _require-vagrant
	vagrant halt

vm-ssh: _require-vagrant
	vagrant ssh

vm-destroy: _require-vagrant
	vagrant destroy -f

logs: _require-vagrant
	vagrant ssh -c "journalctl -f -u 'cafebox-*'"

_require-vagrant:
	@command -v vagrant >/dev/null 2>&1 || { echo "ERROR: vagrant is not installed. See https://developer.hashicorp.com/vagrant/downloads"; exit 1; }
