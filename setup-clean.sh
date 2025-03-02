#!/bin/bash

echo "Cleaning unused files and dependencies..."

rm -rf received venv
find . -type d -name "__pycache__" -exec rm -rf {} +

echo "Unused files and dependencies have been cleared!"