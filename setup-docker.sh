#!/bin/bash

echo "Setting up a docker group..."

groupadd docker
usermod -aG docker $USER

echo "Docker group has been made!"
echo "Please reboot the system from another shell (or with GUI) to activate docker group."
