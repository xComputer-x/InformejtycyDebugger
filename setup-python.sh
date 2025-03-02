#!/bin/bash

echo "Creating virtual enviroment..."

rm -rf venv

python3.12 -m venv venv
source venv/bin/activate

echo "Installing required packages..."

pip3.12 install -r requirements.txt
deactivate

echo "Virtual enviroment has been made!"
