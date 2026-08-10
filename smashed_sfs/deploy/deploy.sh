#!/usr/bin/env bash
# Runs ON THE VPS to pull and apply the latest pushed code. Not run on your
# desktop - you trigger it remotely, e.g.:
#   ssh deploy@your-vps "cd smashed_sfs && ./deploy.sh"
#
# First-time setup only (not part of every deploy):
#   git clone https://github.com/civ1977/smashed_sfs_project.git smashed_sfs
#   cd smashed_sfs
#   python3 -m venv venv
#   cp deploy/.env.example .env   # then fill in real values
#   chmod +x deploy/deploy.sh
#   sudo cp deploy/gunicorn.service /etc/systemd/system/smashed_sfs.service
#   sudo systemctl daemon-reload && sudo systemctl enable --now smashed_sfs
#   sudo cp deploy/nginx.conf /etc/nginx/sites-available/smashed_sfs
#   sudo ln -s /etc/nginx/sites-available/smashed_sfs /etc/nginx/sites-enabled/
#   sudo nginx -t && sudo systemctl reload nginx

set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Pulling latest code"
git pull origin main

echo "==> Installing/updating dependencies"
source venv/bin/activate
pip install -r requirements.txt --quiet

echo "==> Applying migrations"
python manage.py migrate --noinput

echo "==> Collecting static files"
python manage.py collectstatic --noinput

echo "==> Restarting app"
sudo systemctl restart smashed_sfs

echo "==> Done. Recent logs:"
sudo journalctl -u smashed_sfs -n 15 --no-pager
