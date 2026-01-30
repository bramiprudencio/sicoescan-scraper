#!/bin/bash

# Start Xvfb in the background
Xvfb :99 -screen 0 1920x1080x24 &

# Set the DISPLAY environment variable so Chrome uses it
export DISPLAY=:99

# Run the Python script
python scraper.py