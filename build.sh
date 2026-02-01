#!/bin/bash
cd MergedApp
npm install
VITE_API_BASE=https://ws-trader-pulse.onrender.com npm run build
