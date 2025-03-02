#!/bin/bash

echo "Running server..."
printf "\033[38:5:218mWarning:\033[0m this is only for testing. On the server use \"gunicorn\" instead\n"

app_dir=debugger/src

venv/bin/python3.13 $app_dir/app.py 