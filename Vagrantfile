# Vagrantfile — CafeBox development VM
#
# Usage:
#   vagrant up        Start (and provision on first run)
#   vagrant halt      Stop the VM
#   vagrant ssh       Open a shell inside the VM
#   vagrant destroy   Remove the VM entirely
#
# Or use the Makefile shortcuts:  make vm-start / vm-stop / vm-ssh / vm-destroy

Vagrant.configure("2") do |config|
  config.vm.box = "debian/trixie64"
  config.vm.hostname = "cafebox-dev"

  # Portal (nginx on port 80) → http://localhost:8080 on the host
  config.vm.network "forwarded_port", guest: 80,   host: 8080, host_ip: "127.0.0.1"
  # Admin backend                  → http://localhost:8000 on the host
  config.vm.network "forwarded_port", guest: 8000, host: 8000, host_ip: "127.0.0.1"

  # Repo root is always available at /vagrant inside the VM
  # NFSv3 avoids the NFSv4 pseudo-root (fsid=0) requirement that causes
  # "No such file or directory" mount failures with the default vers=4.
  config.vm.synced_folder ".", "/vagrant",
    type: "nfs",
    nfs_version: 3,
    #TODO enable nfs it currently fails with an error when enabled
    disabled: true

  config.vm.provider "libvirt" do |vb|
    vb.memory = 1024
    vb.cpus   = 2
  end

  # Provision using Ansible — the same playbook is used for real Pi hardware
  config.vm.provision "ansible" do |ansible|
    ansible.playbook   = "ansible/site.yml"
    # Allow the host to reach the portal via VirtualBox NAT (eth0).
    # In production (real Pi) this variable is left blank and has no effect.
    ansible.extra_vars = {
      "firewall_management_interface" => "eth0",
      # Deploy diagnostic scripts inside the VM (dev only; false by default in production).
      # Override for production: ansible-playbook -i inventory/production site.yml -e diagnostics_enabled=true
      "diagnostics_enabled" => true
    }
    #TODO get inventory working so we can target just the vm instead of all hosts.
    # ansible.inventory_path = "ansible/inventory/development"
  end
end
