# Vagrantfile — Hearth development VM
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
  config.vm.hostname = "hearth-dev"

  # Portal (nginx on port 80) → http://localhost:8080 on the host
  config.vm.network "forwarded_port", guest: 80,   host: 8080, host_ip: "127.0.0.1"

  # Repo root is always available at /vagrant inside the VM
  # NFSv3 avoids the NFSv4 pseudo-root (fsid=0) requirement that causes
  # "No such file or directory" mount failures with the default vers=4.
  config.vm.synced_folder ".", "/vagrant",
    type: "nfs",
    nfs_version: 3

  config.vm.provider "libvirt" do |vb|
    vb.memory = 1024
    vb.cpus   = 2
  end

  # Provision using Ansible — the same playbook is used for real Pi hardware
  config.vm.provision "ansible" do |ansible|
    ansible.playbook   = "ansible/site.yml"
    # ansible.verbose = "vvv"
    # Allow the host to reach the portal via VirtualBox NAT (eth0).
    # In production (real Pi) this variable is left blank and has no effect.
    ansible.host_key_checking = false
    ansible.extra_vars = {
      "firewall_management_interface" => "eth0",
      # Deploy diagnostic scripts inside the VM (dev only; false by default in production).
      # Override for production: ansible-playbook -i inventory/production site.yml -e diagnostics_enabled=true
      "diagnostics_enabled" => true,
      # Captive portal is a WiFi AP feature — it intercepts requests based on Host
      # header, which means localhost:8080 dev access gets redirected to an
      # unresolvable hearth.local address.  Disabled in dev; enabled in production
      # via hearth.yaml.  scripts/test-vagrant.sh detects the live state from the
      # rendered nginx config, not hearth.yaml, so tests stay honest.
      "captive_portal" => {"enabled" => false}
    }
    #TODO get inventory working so we can target just the vm instead of all hosts.
    # ansible.inventory_path = "ansible/inventory/development"
  end
end
