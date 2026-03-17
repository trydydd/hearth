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
  config.vm.synced_folder ".", "/vagrant"

  config.vm.provider "virtualbox" do |vb|
    vb.name   = "cafebox-dev"
    vb.memory = 1024
    vb.cpus   = 2
  end

  # Provision using Ansible — the same playbook is used for real Pi hardware
  config.vm.provision "ansible" do |ansible|
    ansible.playbook = "ansible/site.yml"
  end
end
