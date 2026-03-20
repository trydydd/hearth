# diagnostics role

Deploys developer diagnostic scripts into a directory inside the target host.

## Default behaviour

Deployment is **off by default** (`diagnostics_enabled: false`). This means:

- Running `ansible-playbook -i inventory/production site.yml` does **nothing** for
  this role — no files are written to the Pi.
- Running `vagrant up` / `vagrant provision` automatically enables the role because
  the Vagrantfile passes `diagnostics_enabled: true` via `extra_vars`.

## Deployed scripts

| Script | Installed path | Purpose |
|--------|---------------|---------|
| `diagnose-first-boot.sh` | `/usr/local/share/cafebox/diag/diagnose-first-boot.sh` | Checks the full first-boot credential chain: system users → service status & journal → portal root files → portal root HTTP response → API status endpoint → nginx error & access logs → network interfaces → nftables ruleset → listening ports |

## Running a diagnostic script (development VM)

```bash
vagrant ssh -- sudo /usr/local/share/cafebox/diag/diagnose-first-boot.sh
```

Paste the full output into a GitHub issue when reporting a problem.

### Reading the output

Key things to check when the portal is not loading in the host browser:

- **Section 7 (portal root)** — `index.html` must be present. If it is missing,
  re-provision: `vagrant provision`.
- **Section 8 (root HTTP)** — `GET http://localhost/ → HTTP 200` must appear. A
  non-200 response means nginx cannot serve the portal page from inside the VM.
- **Section 11 (access log)** — If the log is *empty* after you tried to open the
  portal in a browser, no request has reached nginx. This means VirtualBox port
  forwarding is not delivering traffic. Run `vagrant reload` to re-apply the port
  forward rules.
- **Section 12 (interfaces)** — Shows the actual NIC names in the VM. The
  nftables rules use a negative match (`iifname != "wlan0"`) so they work
  regardless of whether the NIC is called `eth0`, `enp0s3`, or anything else.

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `diagnostics_enabled` | `false` | Set to `true` to deploy scripts. Enabled automatically in the dev VM via Vagrantfile. |
| `diagnostics_dir` | `/usr/local/share/cafebox/diag` | Directory on the target host where scripts are installed. |

## Deploying to production (override)

If you need to run a diagnostic script on a real Pi, pass the flag on the command
line — nothing needs to be changed in the playbook or inventory:

```bash
ansible-playbook -i inventory/production site.yml -e diagnostics_enabled=true
```

The scripts are installed to `diagnostics_dir` and can then be run over SSH:

```bash
ssh pi@<host> sudo /usr/local/share/cafebox/diag/diagnose-first-boot.sh
```

Remove the scripts afterwards if desired:

```bash
ssh pi@<host> sudo rm -rf /usr/local/share/cafebox/diag
```
