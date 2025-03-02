#!/bin/bash

echo "Installing required software..."

apt-get update -y
apt-get upgrade -y
snap refresh

apt install -y --no-install-recommends python3.13 python3.13-venv python3-pip python3-gunicorn gunicorn gcc
snap install docker --channel=stable --classic

apt-get clean
apt-get autoremove -y

echo "Software installed..."