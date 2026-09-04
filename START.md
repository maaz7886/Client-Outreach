# 🚀 College Outreach System — Step-by-Step Setup & Getting Started Guide

Welcome to the **College Outreach System**. This guide provides complete step-by-step instructions for getting the entire project up and running from scratch on a new machine or desktop environment.

---

## 📋 System Architecture Overview

The system runs using a hybrid local setup:
- **Backend & Services (Docker Containers):**
  - **PostgreSQL 16:** Relational database (`db` container)
  - **Redis 7:** Celery task queue & caching (`redis` container)
  - **FastAPI API:** Main web service on `http://localhost:8000` (`api` container)
  - **Celery Worker:** Background task processor for AI drafting, email sending, web crawling (`worker` container)
  - **Celery Beat:** Scheduled cron job runner (`beat` container)
- **Frontend (Host Node.js):**
  - **Next.js 16 (React 19):** Web Application on `http://localhost:3000`

---

## 🛠️ Step 0: Prerequisites Check

Before starting, ensure the following software is installed on your machine:

1. **Docker Desktop** (Must be running): [Download Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. **Node.js (v18 or v20+)** & **npm**: Verify with `node -v` and `npm -v`
3. **Git**: Verify with `git --version`

---

## 🚀 Step-by-Step Desktop Setup Instructions

### Step 1: Copy / Clone the Repository to Desktop

Open your terminal (PowerShell, Command Prompt, or Bash) and navigate to your project directory.

```bash
cd desktop
git clone <your-repository-url> college-outreach-system
cd college-outreach-system
```

**Expected Outcome:**
```text
Cloning into 'college-outreach-system'...
remote: Enumerating objects: ... done.
Unpacking objects: 100% ... done.
```

---

### Step 2: Create and Configure the Environment File (`.env`)

Copy `.env.example` to create `.env` at the root of the project repository.

#### On Windows (PowerShell / CMD):
```powershell
copy .env.example .env
```

#### On Linux / macOS (Bash):
```bash
cp .env.example .env
```

**Expected Outcome:**
A file named `.env` will be generated in your project root directory.

#### Edit `.env` with your actual credentials:
Open `.env` in your text editor (VS Code, Notepad, etc.) and update the critical keys:

```env
# 1. Database Password
POSTGRES_PASSWORD=my_secure_postgres_password_123

# 2. JWT Secret key (generate a random 64-char string)
JWT_SECRET=super_secret_jwt_token_key_change_this_to_a_long_random_string_12345

# 3. LLM API Key (Groq Free Tier: https://console.groq.com)
LLM_PROVIDER=groq
LLM_API_KEY=gsk_your_groq_api_key_here

# 4. URLs
PUBLIC_BASE_URL=http://localhost:8000
PUBLIC_API_URL=http://localhost:8000
CORS_ORIGINS=http://localhost:3000

# 5. SMTP Email Credentials (Gmail App Password or SMTP Service)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SENDER_NAME=College Outreach Team
SENDER_EMAIL=your-email@gmail.com
SENDER_POSTAL_ADDRESS=123 Main Street, City, State 10001
```

---

### Step 3: Build Docker Images Locally & Start Container Services

Since we are running backend services locally via Docker, **you must build the backend Docker images on your setup**.

Run the following command from the project root:

```bash
docker compose up -d --build
```

**Expected Outcome:**
```text
[+] Building 45.2s (12/12) FINISHED
 => [api internal] load build definition from Dockerfile
 => [worker internal] load build definition from Dockerfile
 => [api] exporting to image
 => [api] naming to docker.io/library/college-outreach-system-api
 => [worker] naming to docker.io/library/college-outreach-system-worker
[+] Running 5/5
 ✔ Container college-outreach-system-db-1      Healthy                                            0.5s
 ✔ Container college-outreach-system-redis-1   Healthy                                            0.5s
 ✔ Container college-outreach-system-api-1     Started                                            0.8s
 ✔ Container college-outreach-system-worker-1  Started                                            0.8s
 ✔ Container college-outreach-system-beat-1    Started                                            0.8s
```

---

### Step 4: Verify Container Health Status

Check that all container services are running properly:

```bash
docker compose ps
```

**Expected Outcome:**
```text
NAME                               IMAGE                            COMMAND                  SERVICE   CREATED          STATUS                    PORTS
college-outreach-system-api-1      college-outreach-system-api      "/entrypoint.sh api"     api       10 seconds ago   Up 9 seconds              127.0.0.1:8000->8000/tcp
college-outreach-system-beat-1     college-outreach-system-worker   "/entrypoint.sh beat"    beat      10 seconds ago   Up 9 seconds              
college-outreach-system-db-1       postgres:16-alpine               "docker-entrypoint.s…"   db        10 seconds ago   Up 10 seconds (healthy)   
college-outreach-system-redis-1    redis:7-alpine                   "docker-entrypoint.s…"   redis     10 seconds ago   Up 10 seconds (healthy)   
college-outreach-system-worker-1   college-outreach-system-worker   "/entrypoint.sh worker"  worker    10 seconds ago   Up 9 seconds              
```

---

### Step 5: Run Database Migrations (Alembic)

Now apply all database table schemas and updates using Alembic inside the running `api` container.

```bash
docker compose exec api alembic upgrade head
```

**Expected Outcome:**
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> a1b2c3d4e5f6, initial_tables
...
INFO  [alembic.runtime.migration] Running upgrade e5f6a7b8c9d0 -> g6e5f3c7b18d, add_campaign_id_and_list_id_to_attachments
```

---

### Step 6: Verify Backend API Health Endpoint

Verify that the backend FastAPI engine is responding correctly.

```bash
curl http://localhost:8000/api/v1/health
```

#### On PowerShell (if `curl` is aliased):
```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health
```

**Expected Outcome:**
```json
{"status":"ok"}
```

---

### Step 7: Install Frontend Dependencies & Start Frontend Dev Server

Open a terminal in the `frontend` folder (or open a new terminal window):

```bash
cd frontend
npm install
npm run dev
```

**Expected Outcome:**
```text
  ▲ Next.js 16.2.10
  - Local:        http://localhost:3000
  - Network:      http://192.168.x.x:3000

 ✓ Starting...
 ✓ Ready in 1.8s
```

Now open **`http://localhost:3000`** in your browser!

---

## 🛠️ Essential Maintenance & Workflow Commands

### 🔄 How to Rebuild Docker Images (After Editing Backend Code)

When you make changes to Python files inside `backend/` or update dependencies in `pyproject.toml`, Docker containers need to incorporate the updated files. Rebuild and restart the containers with:

```bash
docker compose up -d --build api worker beat
```

**Force Clean Rebuild (No Cache):**
If changes do not reflect, perform a clean rebuild:
```bash
docker compose build --no-cache api worker beat
docker compose up -d api worker beat
```

**Expected Outcome:**
```text
[+] Building 15.4s (12/12) FINISHED
[+] Running 3/3
 ✔ Container college-outreach-system-api-1     Recreated                                          0.6s
 ✔ Container college-outreach-system-worker-1  Recreated                                          0.6s
 ✔ Container college-outreach-system-beat-1    Recreated                                          0.6s
```

---

### 🪵 How to Inspect Logs

To debug background tasks, email sending logs, or API errors:

#### View all backend logs in real time:
```bash
docker compose logs -f api worker
```

#### View specific service logs (e.g. Celery worker):
```bash
docker compose logs -f worker
```

**Expected Outcome:**
Shows live streaming stdout/stderr logs from the containers (e.g., Celery task execution logs, HTTP requests). Press `Ctrl + C` to stop viewing.

---

### ⏹️ How to Stop and Restart the Project

#### Stop all running backend containers:
```bash
docker compose stop
```
**Expected Outcome:**
```text
[+] Stopping 5/5
 ✔ Container college-outreach-system-beat-1    Stopped                                            0.5s
 ✔ Container college-outreach-system-worker-1  Stopped                                            0.5s
 ✔ Container college-outreach-system-api-1     Stopped                                            0.5s
 ✔ Container college-outreach-system-redis-1   Stopped                                            0.3s
 ✔ Container college-outreach-system-db-1      Stopped                                            0.4s
```

#### Restart stopped backend containers:
```bash
docker compose start
```

#### Completely bring down containers (keeps database volumes intact):
```bash
docker compose down
```

---

## ⚡ Quick One-Command Local Startup (Root Directory)

Root `package.json` contains shortcut scripts to run backend and frontend together:

```bash
# Start backend containers and frontend together
npm run dev

# Stop backend containers
npm run stop

# View live backend logs
npm run logs
```

---

## 🎯 Summary Checklist

| Action | Command | Expected Result |
| :--- | :--- | :--- |
| **Setup Env** | `copy .env.example .env` | `.env` created |
| **Build & Run Docker** | `docker compose up -d --build` | 5 containers started & healthy |
| **Run Migrations** | `docker compose exec api alembic upgrade head` | `head` migration applied |
| **Check API Health** | `curl http://localhost:8000/api/v1/health` | `{"status":"ok"}` |
| **Start Frontend** | `cd frontend && npm run dev` | Available on `http://localhost:3000` |
| **Rebuild Container** | `docker compose up -d --build api worker` | Containers recreated with updated code |
