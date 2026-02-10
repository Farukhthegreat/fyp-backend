# Database & Environment Configuration Guide

Complete guide for setting up PostgreSQL database and environment variables on a new computer.

---

## 🗄️ PostgreSQL Database Setup

### Step 1: Install PostgreSQL

**Windows:**
1. Download from [postgresql.org/download/windows](https://www.postgresql.org/download/windows/)
2. Run the installer
3. During installation:
   - Set password for `postgres` superuser (**Remember this!**)
   - Default port: `5432`
   - Accept other defaults
4. Verify installation:

```powershell
psql --version
# Should show: psql (PostgreSQL) 14.x or higher
```

**macOS:**
```bash
# Using Homebrew
brew install postgresql@14
brew services start postgresql@14
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
```

---

### Step 2: Create Database and User

Open PowerShell as Administrator (Windows) or Terminal (macOS/Linux):

```powershell
# Connect to PostgreSQL
psql -U postgres

# You'll be prompted for the postgres password you set during installation
```

In the PostgreSQL prompt (`postgres=#`), execute these SQL commands:

```sql
-- Create a dedicated user for the application
CREATE USER aviansense_user WITH PASSWORD 'YourSecurePassword123!';

-- Create the database owned by this user
CREATE DATABASE aviansense_db OWNER aviansense_user;

-- Grant all privileges to the user
GRANT ALL PRIVILEGES ON DATABASE aviansense_db TO aviansense_user;

-- Verify databases exist
\l

-- Verify users exist
\du

-- Exit PostgreSQL
\q
```

**📝 Save These Credentials:**
- Database Name: `aviansense_db`
- Database User: `aviansense_user`
- Database Password: `YourSecurePassword123!` (use your own secure password)
- Database Host: `localhost`
- Database Port: `5432`

---

### Step 3: Test Database Connection

Verify you can connect with the new user:

```powershell
psql -U aviansense_user -d aviansense_db -h localhost

# If successful, you'll see:
# aviansense_db=>

# Exit with:
\q
```

**Troubleshooting Connection Issues:**
- Ensure PostgreSQL service is running
- Check firewall allows port 5432
- Verify username and password are correct
- On Windows: Services → PostgreSQL should be "Running"

---

## 🔐 Environment Variables Setup

### Step 1: Copy Configuration Template

Navigate to your project directory:

```powershell
# Navigate to backend folder
cd C:\path\to\fyp-backend

# Copy the example template
Copy-Item .env.example .env

# Open for editing
notepad .env
```

---

### Step 2: Configure .env File

Update `.env` with your actual values:

```env
# ============================================
# Django Settings
# ============================================
DEBUG=True
SECRET_KEY=django-insecure-CHANGE-THIS-TO-RANDOM-SECRET-KEY

# ============================================
# Database Configuration
# ============================================
DB_ENGINE=django.db.backends.postgresql
DB_NAME=aviansense_db
DB_USER=aviansense_user
DB_PASSWORD=YourSecurePassword123!
DB_HOST=localhost
DB_PORT=5432

# ============================================
# Firebase Configuration
# ============================================
FIREBASE_CREDENTIALS_PATH=firebase-credentials.json

# ============================================
# CORS and Server Settings
# ============================================
ALLOWED_HOSTS=localhost,127.0.0.1

# ============================================
# Server Configuration
# ============================================
SERVER_PORT=8000
SERVER_HOST=0.0.0.0
```

---

### Step 3: Generate SECRET_KEY

**Option 1: Using Django (Recommended)**
```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

**Option 2: Using Python**
```powershell
python -c "import secrets; print('django-insecure-' + secrets.token_urlsafe(50))"
```

Copy the output and paste it into `.env` as the `SECRET_KEY` value.

---

### Step 4: Add Firebase Credentials

#### Get Firebase Service Account Key:

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project
3. Click ⚙️ **Settings** → **Service Accounts**
4. Click **"Generate New Private Key"**
5. Click **"Generate Key"** to download JSON file

#### Save to Project:

```powershell
# Move downloaded file to project root
Move-Item "C:\Users\YourName\Downloads\your-project-firebase-adminsdk.json" "C:\path\to\fyp-backend\firebase-credentials.json"

# Verify file exists
Test-Path firebase-credentials.json
# Should return: True
```

---

### Step 5: Configure Network Access (Optional)

To allow connections from other devices (phone, tablet, other computers):

#### Find Your Computer's IP Address:

**Windows:**
```powershell
ipconfig
# Look for "IPv4 Address" under your active network adapter
# Example: 192.168.100.12
```

**macOS/Linux:**
```bash
ifconfig
# or
ip addr show
```

#### Update .env with Your IP:

```env
ALLOWED_HOSTS=localhost,127.0.0.1,192.168.100.12
```

Replace `192.168.100.12` with your actual IP address.

---

## ✅ Verification Steps

### Step 1: Install Dependencies

```powershell
# Activate virtual environment
venv\Scripts\Activate.ps1

# Install all packages
pip install -r requirements.txt
```

---

### Step 2: Run Database Migrations

```powershell
# Create database tables
python manage.py migrate

# Expected output:
# Running migrations:
#   Applying contenttypes.0001_initial... OK
#   Applying auth.0001_initial... OK
#   Applying admin.0001_initial... OK
#   Applying api.0001_initial... OK
#   ...
```

---

### Step 3: Create Superuser Account

```powershell
python manage.py createsuperuser

# Enter when prompted:
# Username: admin
# Email: your-email@example.com
# Password: ********
# Password (again): ********
```

---

### Step 4: Start Development Server

```powershell
# Start on localhost only
python manage.py runserver

# OR start on all network interfaces
python manage.py runserver 0.0.0.0:8000
```

---

### Step 5: Test Endpoints

**Health Check:**
```
http://127.0.0.1:8000/api/health/
```

Expected response:
```json
{
    "status": "ok",
    "message": "Backend is running"
}
```

**Admin Panel:**
```
http://127.0.0.1:8000/admin/
```

Login with superuser credentials created in Step 3.

---

## 🚨 Troubleshooting

### Issue: "psql: command not found"

**Solution:** Add PostgreSQL to system PATH

**Windows:**
1. Search → "Environment Variables"
2. System Properties → Environment Variables
3. Edit "Path" under System Variables
4. Add: `C:\Program Files\PostgreSQL\16\bin`
5. Restart PowerShell

---

### Issue: "FATAL: password authentication failed"

**Solutions:**
1. Verify credentials in `.env` match those from Step 2
2. Test connection manually:
   ```powershell
   psql -U aviansense_user -d aviansense_db -h localhost
   ```
3. Reset password if needed:
   ```sql
   -- Connect as postgres
   psql -U postgres
   
   -- Reset password
   ALTER USER aviansense_user WITH PASSWORD 'NewPassword123!';
   ```

---

### Issue: "django.core.exceptions.ImproperlyConfigured"

**Solutions:**
1. Verify `.env` file exists in project root
2. Check all required variables are set
3. Ensure no typos in variable names
4. Verify `.env` is not in `.gitignore` (it should be)
5. Check file encoding is UTF-8

**Verify .env is loaded:**
```powershell
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('DB_NAME:', os.getenv('DB_NAME'))"
```

---

### Issue: "connection to server at localhost failed"

**Solutions:**
1. Check PostgreSQL service is running:
   - **Windows:** Services → PostgreSQL
   - **macOS:** `brew services list`
   - **Linux:** `sudo systemctl status postgresql`

2. Verify port 5432 is listening:
   ```powershell
   netstat -an | findstr "5432"
   ```

3. Check firewall settings allow port 5432

4. Ensure `DB_HOST=localhost` in `.env`

---

### Issue: "FirebaseError: Could not load credentials"

**Solutions:**
1. Verify `firebase-credentials.json` exists in project root
2. Check `FIREBASE_CREDENTIALS_PATH` in `.env` is correct
3. Verify JSON file is valid (open in text editor)
4. Ensure file has proper permissions

---

### Issue: "ModuleNotFoundError: No module named 'psycopg2'"

**Solution:**
```powershell
pip install psycopg2-binary
```

---

### Issue: Can't connect from other devices

**Solutions:**
1. Update `.env`:
   ```env
   ALLOWED_HOSTS=localhost,127.0.0.1,YOUR_IP_ADDRESS
   ```

2. Run server on all interfaces:
   ```powershell
   python manage.py runserver 0.0.0.0:8000
   ```

3. Check firewall allows port 8000:
   - **Windows:** Windows Defender Firewall → Allow an app
   - Add Python to allowed apps

4. Verify devices are on same network

5. Test from other device:
   ```
   http://YOUR_IP_ADDRESS:8000/api/health/
   ```

---

## 📋 Complete Setup Checklist

Use this checklist to verify your setup:

### PostgreSQL Setup
- [ ] PostgreSQL installed and running
- [ ] Database `aviansense_db` created
- [ ] User `aviansense_user` created
- [ ] Privileges granted to user
- [ ] Connection tested successfully

### Environment Configuration
- [ ] `.env` file created from `.env.example`
- [ ] `SECRET_KEY` generated and set
- [ ] Database credentials updated in `.env`
- [ ] `DB_NAME` set to `aviansense_db`
- [ ] `DB_USER` set to `aviansense_user`
- [ ] `DB_PASSWORD` set correctly
- [ ] `DB_HOST` set to `localhost`
- [ ] `DB_PORT` set to `5432`

### Firebase Setup
- [ ] Firebase project created
- [ ] Service account key downloaded
- [ ] Saved as `firebase-credentials.json` in project root
- [ ] `FIREBASE_CREDENTIALS_PATH` set in `.env`

### Django Setup
- [ ] Virtual environment activated
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] Migrations run: `python manage.py migrate`
- [ ] Superuser created: `python manage.py createsuperuser`

### Verification
- [ ] Server starts: `python manage.py runserver`
- [ ] Health endpoint responds: http://127.0.0.1:8000/api/health/
- [ ] Admin panel accessible: http://127.0.0.1:8000/admin/
- [ ] Can login to admin panel

### Network Setup (Optional)
- [ ] Computer's IP address identified
- [ ] IP added to `ALLOWED_HOSTS` in `.env`
- [ ] Server runs on network: `python manage.py runserver 0.0.0.0:8000`
- [ ] Firewall allows port 8000
- [ ] Accessible from other devices

---

## 🔒 Security Best Practices

### Development Environment
- ✅ Use strong passwords for database users
- ✅ Keep `SECRET_KEY` unique and random (50+ characters)
- ✅ Never commit `.env` file to Git (it's in `.gitignore`)
- ✅ Keep `firebase-credentials.json` secure (it's in `.gitignore`)
- ⚠️ `DEBUG=True` is OK for development only

### Production Environment
- ❗ Set `DEBUG=False` in production
- ❗ Use environment-specific `SECRET_KEY` 
- ❗ Use strong database passwords (16+ characters)
- ❗ Restrict `ALLOWED_HOSTS` to your domain only
- ❗ Use PostgreSQL on secure hosting (AWS RDS, Heroku, etc.)
- ❗ Enable HTTPS/SSL certificates
- ❗ Use Firebase security rules
- ❗ Regular database backups
- ❗ Monitor access logs

---

## 📚 Quick Reference

### PostgreSQL Commands

```sql
-- List all databases
\l

-- List all users
\du

-- Connect to database
\c aviansense_db

-- List all tables
\dt

-- Describe table structure
\d table_name

-- Show current database
SELECT current_database();

-- Show current user
SELECT current_user;

-- Exit
\q
```

### Django Management Commands

```powershell
# Database
python manage.py migrate                 # Apply migrations
python manage.py makemigrations          # Create migrations
python manage.py showmigrations          # List migrations
python manage.py sqlmigrate api 0001     # Show SQL for migration

# Users
python manage.py createsuperuser         # Create admin
python manage.py changepassword admin    # Change password

# Server
python manage.py runserver               # Start server (localhost only)
python manage.py runserver 0.0.0.0:8000  # Start server (network)
python manage.py runserver 8080          # Start on different port

# Database shell
python manage.py dbshell                 # PostgreSQL shell
python manage.py shell                   # Django shell

# Utilities
python manage.py check                   # Check for issues
python manage.py test                    # Run tests
```

### Environment Variables Reference

| Variable | Example Value | Description |
|----------|---------------|-------------|
| `DEBUG` | `True` / `False` | Enable debug mode |
| `SECRET_KEY` | `django-insecure-abc123...` | Django secret key |
| `DB_NAME` | `aviansense_db` | Database name |
| `DB_USER` | `aviansense_user` | Database username |
| `DB_PASSWORD` | `YourPassword123!` | Database password |
| `DB_HOST` | `localhost` | Database host |
| `DB_PORT` | `5432` | Database port |
| `FIREBASE_CREDENTIALS_PATH` | `firebase-credentials.json` | Path to Firebase credentials |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Allowed host domains |

---

## 📞 Additional Help

- **Django Documentation:** [docs.djangoproject.com](https://docs.djangoproject.com)
- **PostgreSQL Documentation:** [postgresql.org/docs](https://www.postgresql.org/docs/)
- **Firebase Documentation:** [firebase.google.com/docs](https://firebase.google.com/docs)
- **Main Setup Guide:** [SETUP_GUIDE.md](./SETUP_GUIDE.md)
- **Project README:** [README.md](./README.md)

---

**Estimated Setup Time:** 20-30 minutes

**Last Updated:** February 2026
