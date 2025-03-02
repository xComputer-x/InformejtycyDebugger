#!/bin/bash

echo "Creating virtual enviroment..."

rm -rf venv

python3.13 -m venv venv
source venv/bin/activate

echo "Installing required packages..."

pip3.13 install -r requirements.txt
deactivate

echo "Virtual enviroment has been made!"
