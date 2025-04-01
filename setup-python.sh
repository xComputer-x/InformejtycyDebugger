#!/bin/bash

echo "Creating virtual enviroment..."

rm -rf venv

python3 -m venv venv
source venv/bin/activate

echo "Installing required packages..."

pip3 install -r requirements.txt
deactivate

echo "Virtual enviroment has been made!"
