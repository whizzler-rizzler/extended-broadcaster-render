#!/bin/bash
cd MergedApp
npm install
# Build with empty VITE_API_BASE for same-origin deployment (backend serves frontend)
VITE_API_BASE="" npm run build
