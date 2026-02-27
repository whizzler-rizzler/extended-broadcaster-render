#!/bin/bash
cd MergedApp/backend
exec python -m uvicorn main:app --host 0.0.0.0 --port 5000
