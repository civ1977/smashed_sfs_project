# Deploying to a z.com VPS

Your desktop stays the only place you edit code. Deploying means: commit → push to GitHub →
run one command that tells the VPS to pull and restart. Nothing on the server changes unless
you trigger it.

```
[Desktop]  git commit, git push origin main  --->  [GitHub: civ1977/smashed_sfs_project]
                                                              |
[Desktop]  ssh deploy@vps "cd smashed_sfs && ./deploy.sh"    |  (you run this, on demand)
                                                              v
                                                       [VPS: git pull, migrate,
                                                        collectstatic, restart gunicorn]
```

## 1. Provision the VPS

At z.com, pick:
- **OS**: Ubuntu 22.04 or 24.04 LTS (these instructions assume Ubuntu/Debian + `apt`)
- **Size**: this is a small-to-medium Django app with MySQL on the same box — 1 vCPU / 2GB RAM
  is enough to start; go bigger only once you see it's actually needed
- Note the VPS's **public IP address** once it's provisioned — you'll SSH into that.

If you have a domain, point an `A` record at the VPS's IP now (DNS propagation takes a while,
so starting this early saves time later). Not required to get started — you can use the bare
IP address everywhere below and add a domain later.

## 2. First login and a non-root user

z.com will give you root SSH access (password or key). Log in once as root, then create a
dedicated user for the app instead of running everything as root:

```bash
ssh root@YOUR_VPS_IP

adduser deploy
usermod -aG sudo deploy

# Copy your SSH key so you can log in as `deploy` without a password.
# From your DESKTOP (not the VPS), run:
#   ssh-copy-id deploy@YOUR_VPS_IP
# (Windows without ssh-copy-id: manually append your desktop's ~/.ssh/id_rsa.pub
#  content to /home/deploy/.ssh/authorized_keys on the VPS.)
```

From here on, SSH in as `deploy`, not `root`:

```bash
ssh deploy@YOUR_VPS_IP
```

## 3. Install the stack

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git mysql-server nginx
```

## 4. Set up MySQL on the VPS

```bash
sudo mysql_secure_installation   # set a root password, decline the rest is fine

sudo mysql -u root -p
```
```sql
CREATE DATABASE smashed_sfs CHARACTER SET utf8mb4;
-- Using root directly (matching settings.py's default DB_USER) is fine for
-- a single-app VPS; create a dedicated MySQL user instead if you prefer.
ALTER USER 'root'@'localhost' IDENTIFIED BY 'a-real-password-here';
FLUSH PRIVILEGES;
EXIT;
```

Remember that password — it goes in `.env` as `DB_PASSWORD` in step 6.

## 5. Get the code onto the VPS

```bash
cd ~
git clone https://github.com/civ1977/smashed_sfs_project.git smashed_sfs
cd smashed_sfs

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

Open the firewall:
```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

Visit `http://YOUR_VPS_IP` (or your domain) — the app should be live.

## 9. HTTPS (once you have a domain pointed at the VPS)

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
ssh deploy@YOUR_VPS_IP "cd smashed_sfs && ./deploy.sh"
```

That's it — one SSH command runs `git pull`, installs any new dependencies, applies new
migrations, collects static files, and restarts gunicorn. If a migration or dependency
install fails, `deploy.sh` stops immediately (`set -e`) rather than restarting into a broken
state — check the error output, fix it, push again, redeploy.

To avoid typing the full SSH command every time, add this to your desktop's SSH config
(`~/.ssh/config`, or `C:\Users\<you>\.ssh\config` on Windows):
```
Host smashed-vps
    HostName YOUR_VPS_IP
    User deploy
```
Then deploying is just:
```bash
ssh smashed-vps "cd smashed_sfs && ./deploy.sh"
```

## Notes

- **Backups**: nothing here backs up the MySQL database automatically. At minimum, set up a
  cron job on the VPS running `mysqldump` on a schedule, copied somewhere off the VPS itself.
- **Logs**: `sudo journalctl -u smashed_sfs -f` for the live app process; `logs/django.log` in
  the project directory for ERROR-level application logs (per `settings.py`'s `LOGGING` config).
- **Rolling back**: since this is a normal git history, `git log` on the VPS + `git reset --hard
  <previous-commit>` + rerun the last few steps of `deploy.sh` by hand gets you back to a known
  state if a deploy goes wrong.
