#!/bin/sh
flask deploy
exec gunicorn -b :5000 papermill_api:app