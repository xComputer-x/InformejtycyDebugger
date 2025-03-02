#!/bin/bash

echo "Setting up a docker group..."

groupadd docker
usermod -aG docker $USER

echo "Docker group has been made!"
echo "Please reboot the system or type 'su - $USER'. Note, that unless you reboot your system, you must re type 'su - $USER' every time new terminal is created."
