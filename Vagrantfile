# Vagrantfile — CafeBox development VM
#
# Provisions a headless Debian 13 "trixie" VM and configures it with Ansible.
#
# Prerequisites:
#   vagrant          (https://www.vagrantup.com)
#   VirtualBox       (https://www.virtualbox.org) or another supported provider
#   ansible-playbook (https://www.ansible.com)
#
# Usage:
#   vagrant up          # create and provision the VM
#   vagrant provision   # re-run Ansible provisioning
#   vagrant ssh         # open a shell in the VM
#   vagrant halt        # shut down the VM
#   vagrant destroy     # delete the VM entirely

Vagrant.configure("2") do |config|
  config.vm.box = "debian/trixie64"

  config.vm.hostname = "cafebox-dev"

  # Forward the nginx port so the portal is accessible at http://localhost:8080
  config.vm.network "forwarded_port", guest: 80, host: 8080, host_ip: "127.0.0.1"

  config.vm.provider "virtualbox" do |vb|
    vb.name   = "cafebox-dev"
    vb.memory = "1024"
    vb.cpus   = 2
    vb.gui    = false
  end

  # Share the repository root into the VM
  config.vm.synced_folder ".", "/vagrant", type: "virtualbox"

  # Ansible provisioner — runs ansible/playbook.yml inside the VM
  config.vm.provision "ansible" do |ansible|
    ansible.playbook   = "ansible/playbook.yml"
    ansible.inventory_path = "ansible/inventory.yml"
    ansible.verbose    = false
  end
end
