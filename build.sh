#!/bin/bash
set -e
cd MergedApp
npm install
pip install -r backend/requirements.txt
VITE_API_BASE="" npm run build
