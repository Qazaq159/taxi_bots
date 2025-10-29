#!/bin/bash

cd taxi_bot
python manage.py collectstatic --no-input
python manage.py migrate --no-input