#!/usr/bin/env bash
# Runs ON THE VPS to pull and apply the latest pushed code. Not run on your
# desktop - you trigger it remotely, e.g.:
#   ssh deploy@your-vps "cd smashed_sfs/smashed_sfs && ./deploy.sh"
#
# First-time setup only (not part of every deploy). Note the repo nests the
# actual Django project one level deeper than the checkout - manage.py etc.
# end up at ~/smashed_sfs/smashed_sfs/, which is where venv/.env/deploy.sh
# all live too:
#   git clone https://github.com/civ1977/smashed_sfs_project.git smashed_sfs
#   cd smashed_sfs/smashed_sfs
#   python3 -m venv venv
#   cp deploy/.env.example .env   # then fill in real values
#   chmod +x deploy/deploy.sh
#   sudo cp deploy/gunicorn.service /etc/systemd/system/smashed_sfs.service
#   sudo systemctl daemon-reload && sudo systemctl enable --now smashed_sfs
#   sudo cp deploy/nginx.conf /etc/nginx/sites-available/smashed_sfs
#   sudo ln -s /etc/nginx/sites-available/smashed_sfs /etc/nginx/sites-enabled/
#   sudo nginx -t && sudo systemctl reload nginx

set -euo pipefail

# The GitHub repo nests the actual Django project one level deeper than the
# checkout root (~/smashed_sfs/smashed_sfs/, not ~/smashed_sfs/) - this
# script lives inside that inner directory's deploy/ folder, so APP_DIR is
# one level up from here, and REPO_ROOT (where .git actually lives) is one
# level up again.
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$APP_DIR/.." && pwd)"

echo "==> Pulling latest code"
cd "$REPO_ROOT"
git pull origin main

echo "==> Installing/updating dependencies"
cd "$APP_DIR"
source venv/bin/activate
pip install -r requirements.txt --quiet

echo "==> Applying migrations"
python manage.py migrate --noinput

echo "==> Refreshing GeoIP database"
python deploy/download_geoip_db.py

echo "==> Collecting static files"
python manage.py collectstatic --noinput

echo "==> Restarting app"
sudo systemctl restart smashed_sfs

echo "==> Done. Recent logs:"
sudo journalctl -u smashed_sfs -n 15 --no-pager
