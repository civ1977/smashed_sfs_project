# Deploying to Oracle Cloud (Always Free tier)

Your desktop stays the only place you edit code. Deploying means: commit → push to GitHub →
run one command that tells the VM to pull and restart. Nothing on the server changes unless
you trigger it.

```
[Desktop]  git commit, git push origin main  --->  [GitHub: civ1977/smashed_sfs_project]
                                                              |
[Desktop]  ssh deploy@vm "cd smashed_sfs && ./deploy.sh"     |  (you run this, on demand)
                                                              v
                                                       [OCI VM: git pull, migrate,
                                                        collectstatic, restart gunicorn]
```

## 1. Create the instance in the OCI console

In the Oracle Cloud console: **Compute → Instances → Create Instance**.
- **Image**: Ubuntu 22.04 or 24.04 (these instructions assume Ubuntu/Debian + `apt`)
- **Shape**: Ampere A1 (Arm), Always Free-eligible — 2 OCPU / 12GB RAM is comfortably enough for
  this app; don't allocate the full free-tier limit if you plan to run anything else on the
  same tenancy later
- **SSH keys**: let OCI generate a key pair for you (download the private key), or paste your
  desktop's own public key (`~/.ssh/id_rsa.pub` / `id_ed25519.pub`) — either way, note where the
  matching private key lives on your desktop, you'll need it for every `ssh`/`scp` command below
- Leave networking on the default VCN/subnet unless you already have a reason not to

Once it's running, note the instance's **public IP address** from the instance detail page.

If you have a domain, point an `A` record at that IP now (DNS propagation takes a while, so
starting this early saves time later). Not required to get started — you can use the bare IP
address everywhere below and add a domain later.

## 2. First login

Oracle's Ubuntu images don't allow direct root SSH login — the default user is `ubuntu`, which
already has passwordless `sudo`:

```bash
ssh -i /path/to/your-private-key ubuntu@YOUR_INSTANCE_IP
```

Create a dedicated app user instead of running everything as `ubuntu`:

```bash
sudo adduser deploy
sudo usermod -aG sudo deploy

# Copy your SSH key so you can log in as `deploy` without a password.
# From your DESKTOP (not the VM), run:
#   ssh-copy-id -i /path/to/your-private-key.pub deploy@YOUR_INSTANCE_IP
# (Windows without ssh-copy-id: manually append the public key's content to
#  /home/deploy/.ssh/authorized_keys on the VM.)
```

From here on, SSH in as `deploy`, not `ubuntu`:

```bash
ssh -i /path/to/your-private-key deploy@YOUR_INSTANCE_IP
```

## 3. Install the stack

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git mysql-server nginx
```

## 4. Set up MySQL on the instance

```bash
sudo mysql_secure_installation   # set a root password, decline the rest is fine

sudo mysql -u root -p
```
```sql
CREATE DATABASE smashed_sfs CHARACTER SET utf8mb4;

-- settings.py refuses to start with root - it requires a least-privilege
-- user scoped to just this one database.
CREATE USER 'smashed_sfs_app'@'localhost' IDENTIFIED BY 'a-real-password-here';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP, REFERENCES
    ON smashed_sfs.* TO 'smashed_sfs_app'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

Remember that password — it goes in `.env` as `DB_PASSWORD` (with `DB_USER=smashed_sfs_app`) in step 6.

## 5. Get the code onto the instance

The GitHub repo nests the actual Django project one level deeper than the checkout root —
`manage.py`, `requirements.txt`, etc. live at `smashed_sfs/smashed_sfs/`, not `smashed_sfs/`.
Every path from here on (venv, `.env`, `deploy.sh`) refers to that inner directory.

```bash
cd ~
git clone https://github.com/civ1977/smashed_sfs_project.git smashed_sfs
cd smashed_sfs/smashed_sfs

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 6. Configure environment variables

```bash
cp deploy/.env.example .env
nano .env    # fill in DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, DB_PASSWORD, etc.
```

Generate a real secret key:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## 7. First-time database setup

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser   # for /admin/ access
```

## 8. Wire up gunicorn + nginx

```bash
chmod +x deploy/deploy.sh

sudo cp deploy/gunicorn.service /etc/systemd/system/smashed_sfs.service
sudo systemctl daemon-reload
sudo systemctl enable --now smashed_sfs
sudo systemctl status smashed_sfs   # should show "active (running)"

sudo cp deploy/nginx.conf /etc/nginx/sites-available/smashed_sfs
sudo nano /etc/nginx/sites-available/smashed_sfs   # replace YOUR_DOMAIN_OR_IP
sudo ln -s /etc/nginx/sites-available/smashed_sfs /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default   # remove nginx's default placeholder site
sudo nginx -t
sudo systemctl reload nginx
```

**Oracle Cloud has two separate firewalls, both of which have to allow the traffic** — this is
the single most common reason a fresh OCI instance is unreachable even after nginx is running:

1. **The OS firewall on the instance itself.** Oracle's Ubuntu image also pre-loads `iptables`
   rules (separate from `ufw`) that only allow SSH in by default. Clear those first so `ufw`
   is actually in charge:
   ```bash
   sudo iptables -F
   sudo netfilter-persistent save || sudo apt install -y iptables-persistent && sudo netfilter-persistent save

   sudo ufw allow OpenSSH
   sudo ufw allow 'Nginx Full'
   sudo ufw enable
   ```

2. **The cloud-level Security List, in the OCI console** (not on the instance at all):
   **Networking → Virtual Cloud Networks → (your VCN) → Security Lists → Default Security
   List → Add Ingress Rules**. Add rules for:
   - Source `0.0.0.0/0`, TCP, destination port `80`
   - Source `0.0.0.0/0`, TCP, destination port `443` (once you set up HTTPS in step 9)

   Port 22 (SSH) is already open here by default — that's why you could SSH in at all — but 80
   and 443 are not, until you add them.

Both have to be open — missing either one looks identical from your end (the page just never
loads), so if it's not working, check both.

Visit `http://YOUR_INSTANCE_IP` (or your domain) — the app should be live.

## 9. HTTPS (once you have a domain pointed at the instance)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

Certbot edits the nginx config to add HTTPS and sets up auto-renewal. Afterward, add
`https://your-domain.com` to `DJANGO_CSRF_TRUSTED_ORIGINS` in `.env` and
`sudo systemctl restart smashed_sfs`.

## 10. Everyday deploys, from your desktop

This is the part you asked for — nothing on the server changes until you say so:

```bash
# On your desktop, after committing your changes:
git push origin main

# Then, still on your desktop, trigger the deploy:
ssh -i /path/to/your-private-key deploy@YOUR_INSTANCE_IP "cd smashed_sfs && ./deploy.sh"
```

That's it — one SSH command runs `git pull`, installs any new dependencies, applies new
migrations, collects static files, and restarts gunicorn. If a migration or dependency
install fails, `deploy.sh` stops immediately (`set -e`) rather than restarting into a broken
state — check the error output, fix it, push again, redeploy.

To avoid typing the full SSH command every time, add this to your desktop's SSH config
(`~/.ssh/config`, or `C:\Users\<you>\.ssh\config` on Windows):
```
Host smashed-oci
    HostName YOUR_INSTANCE_IP
    User deploy
    IdentityFile /path/to/your-private-key
```
Then deploying is just:
```bash
ssh smashed-oci "cd smashed_sfs && ./deploy.sh"
```

## Notes

- **Backups**: nothing here backs up the MySQL database automatically. At minimum, set up a
  cron job on the instance running `mysqldump` on a schedule, copied somewhere off the instance
  itself — OCI's 200GB Always Free block storage doesn't protect against you deleting the wrong
  thing, only against disk failure.
- **Logs**: `sudo journalctl -u smashed_sfs -f` for the live app process; `logs/django.log` in
  the project directory for ERROR-level application logs (per `settings.py`'s `LOGGING` config).
- **Rolling back**: since this is a normal git history, `git log` on the instance + `git reset
  --hard <previous-commit>` + rerun the last few steps of `deploy.sh` by hand gets you back to a
  known state if a deploy goes wrong.
- **Ampere A1 capacity errors**: if OCI says "out of host capacity" when creating the instance,
  that's a known, common Always-Free-tier issue (Ampere A1 is popular and regionally limited) —
  retry, try a different Availability Domain, or fall back to the 2× AMD Micro shape instead.
