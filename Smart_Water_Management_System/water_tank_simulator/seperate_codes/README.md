# Smart Water Management System - Water Tank Simulator

This directory contains the full-stack implementation of a **Water Tank Simulator**. The application simulates water levels in multiple tanks based on historical CSV data, providing a real-time dashboard for monitoring and control.

The system is built using a microservices architecture with **FastAPI** (Backend), **Streamlit** (Frontend), and **Redis** (Optional, for event pub/sub), all containerized using **Docker**.

---

## 🏗️ Architecture

The application consists of three main components:

1.  **Backend (`backend.py`):** A FastAPI server that manages the simulation logic, processes CSV data, and broadcasts real-time updates via WebSockets/SSE.
2.  **Frontend (`streamlit_frontend.py`):** A Streamlit-based dashboard that allows users to start/stop simulations and visualize tank levels in real-time.
3.  **Redis (Optional):** Acts as a message broker for publishing simulation events, enabling scalable real-time communication.

---

## 🚀 Deployment with Docker

The easiest way to run the application is using Docker Compose.

### Prerequisites
*   Docker and Docker Compose installed.
*   `requirements.txt` files present in the directory (referenced in Dockerfiles).

### Configuration Files
*   **`docker-compose.yml`**: Orchestrates the services (`backend`, `frontend`, `redis`).
    *   **Backend:** Maps port `8000:8000`. Mounts `./data` volume. Depends on Redis.
    *   **Frontend:** Maps port `8502:8502`. Depends on Backend.
    *   **Redis:** Uses `redis:7.2-alpine`. Maps port `6379:6379`.
*   **`Dockerfile.backend`**: Builds the backend image using `python:3.11-slim`. Exposes port 8000.
*   **`Dockerfile.frontend`**: Builds the frontend image using `python:3.11-slim`. Exposes port 8502.

### Running the Application
1.  Build and start the containers:
    ```bash
    docker-compose up --build
    ```
2.  Access the **Frontend Dashboard** at `http://localhost:8502`.
3.  Access the **Backend API Docs** at `http://localhost:8000/docs`.

---

## 🐍 Backend Details (`backend.py`)

The backend is the core of the simulation, responsible for data processing and state management.

### Key Features
*   **CSV Data Loading:**
    *   The `preload_csv` function parses historical water data files (e.g., `Water_History_*.csv`).
    *   It normalizes headers and extracts timestamps and values, handling various date formats.
*   **Simulation Workers:**
    *   Thread-based workers (`worker_loop`) iterate through the loaded data.
    *   They simulate time progression and update the tank state (`LATEST_STATE`).
    *   Events are pushed to an internal `EVENT_QUEUE` and published to Redis (channel: `tank_events`).
*   **Real-time Communication:**
    *   **WebSockets:** `/stream/ws` endpoint for bi-directional real-time data.
    *   **Server-Sent Events (SSE):** `/stream/sse` endpoint for uni-directional updates.
*   **State Management:**
    *   Uses thread-safe locks (`LATEST_LOCK`, `SUBSCRIBERS_LOCK`) to manage shared state and subscriber queues.

### API Endpoints
*   **Control:**
    *   `POST /start`: Starts the simulation workers. Accepts `delay_seconds` and `csv_paths`.
    *   `POST /stop`: Stops all running simulation workers.
*   **Monitoring:**
    *   `GET /status`: Returns the current running status, active tanks, and queue size.
    *   `GET /latest`: Retrieves the most recent data point for all tanks.
    *   `GET /events`: Polls for a batch of recent events from the queue.
    *   `GET /list`: Lists available CSV files.

---

## 🖥️ Frontend Details (`streamlit_frontend.py`)

The frontend provides an interactive user interface to control and monitor the simulation.

### Key Features
*   **Control Panel:**
    *   **Start/Stop Buttons:** Send requests to the backend to control the simulation.
    *   **Status Indicator:** Displays the backend connection status and event queue size.
*   **Live Dashboard:**
    *   **Auto-refresh:** Uses `streamlit_autorefresh` to poll the backend every `POLL_INTERVAL_SEC` (default 1s).
    *   **Visual Tanks:** Renders custom HTML/CSS to visualize water levels dynamically.
    *   **Progress Tracking:** Shows the current step vs. total updates for each tank.
*   **Real-time Charts:**
    *   Maintains a session-based history (`st.session_state.history`) of tank levels.
    *   Uses **Plotly** to render interactive line charts for each tank, updating in real-time.

### Configuration
*   `BACKEND_URL`: Defaults to `http://localhost:8000` (or `http://backend:8000` in Docker).
*   `POLL_INTERVAL_SEC`: Frequency of polling the backend for updates.
*   `MAX_HISTORY_LENGTH`: Limits the number of data points stored for charting to prevent memory issues.
