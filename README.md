# Zenia Yoga

Mobile-first yoga class booking system built with Django.

## What is included

- Instructor workflow through Django admin for creating classes, setting schedules, and controlling capacity.
- Public booking pages where clients can reserve their own place in a class.
- Capacity protection and duplicate email protection per class.
- Responsive, app-like interface with a calm, mindfulness-inspired visual style.
- Static file setup ready for PythonAnywhere-style deployment with WhiteNoise.

## Local setup

1. Copy .env.example to .env and adjust values if needed.
2. Activate the virtual environment in .venv.
3. Run migrations.
4. Create an admin user.
5. Start the development server.

## Useful commands

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## PythonAnywhere notes

- Set environment variables from .env.example in the PythonAnywhere dashboard.
- Point the WSGI file to this project and virtual environment.
- Run collectstatic during deployment.
- Replace the default secret key and allowed hosts before going live.

## Main app structure

- booking.models defines classes and bookings.
- booking.admin provides the instructor management interface.
- booking.views and templates render the public booking flow.