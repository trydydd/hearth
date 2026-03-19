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
| `diagnose-first-boot.sh` | `/usr/local/share/cafebox/diag/diagnose-first-boot.sh` | Checks the full first-boot credential chain: system users → service status & journal → flag/password/JSON files → nginx config → live status endpoint → nftables → listening ports |

## Running a diagnostic script (development VM)

```bash
vagrant ssh -- sudo /usr/local/share/cafebox/diag/diagnose-first-boot.sh
```

Paste the full output into a GitHub issue when reporting a problem.

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
