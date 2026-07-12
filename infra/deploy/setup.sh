#!/bin/bash
set -e

echo "=== OCEN Platform Deployment Setup ==="

# Install nginx
apt-get install -y nginx

# Copy systemd services
cp /opt/platform/infra/deploy/ocen-gateway.service /etc/systemd/system/
cp /opt/platform/infra/deploy/ocen-worker.service /etc/systemd/system/
cp /opt/platform/infra/deploy/ocen-pwa.service /etc/systemd/system/

# Copy nginx config
cp /opt/platform/infra/deploy/nginx.conf /etc/nginx/sites-available/ocen
ln -sf /etc/nginx/sites-available/ocen /etc/nginx/sites-enabled/ocen
rm -f /etc/nginx/sites-enabled/default

# Reload and enable
systemctl daemon-reload
systemctl enable ocen-gateway ocen-worker ocen-pwa nginx
systemctl restart ocen-gateway ocen-worker ocen-pwa nginx

echo "=== Deployment complete ==="
echo "  PWA:     http://$(curl -s ifconfig.me)"
echo "  API:     http://$(curl -s ifconfig.me)/health"
echo "  Direct:  http://$(curl -s ifconfig.me):8000/health"
