# fyp-backend

Django REST backend for the FYP project (Flutter frontend connects later).

## Prerequisites

- Python 3.11+ installed/ Recommended (Python 3.12.10)
- Git installed

## First-time setup (Windows)

1. Clone the repo:
   ```powershell
   git clone https://github.com/Farukhthegreat/fyp-backend.git
   cd fyp-backend
   ```

2. Create and activate virtual environment:
   ```powershell
   python -m venv venv
   venv\Scripts\Activate.ps1
   ```

3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

4. Run database migrations:
   ```powershell
   python manage.py migrate
   ```

5. Start the server:
   ```powershell
   python manage.py runserver
   ```

6. Verify health endpoint:
   - http://127.0.0.1:8000/api/health/

## Common commands

- Create superuser:
  ```powershell
  python manage.py createsuperuser
  ```

- Run tests:
  ```powershell
  python manage.py test
  ```

## Notes

- CORS is currently open for development. Tighten it for production.
