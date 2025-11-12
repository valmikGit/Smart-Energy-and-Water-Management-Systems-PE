# --- STAGE 1: BUILDER ---
# Use a lightweight Python base image for building and dependency installation.
FROM python:3.11-slim AS builder

# Set the working directory
WORKDIR /install

# Since we only explicitly require 'streamlit', we install it directly.
# In a larger project, you would copy and install from requirements.txt here.
RUN pip install --no-cache-dir streamlit

# -----------------------------------------------------------------

# --- STAGE 2: FINAL PRODUCTION IMAGE ---
# Use a minimal runtime image for deployment.
FROM python:3.11-slim AS final

# Set the working directory for the application
WORKDIR /app

# Copy the installed packages from the builder stage
# This ensures we don't bring in unnecessary build tools or cache files.
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy the application code
COPY app.py .

# Expose the default Streamlit port
EXPOSE 8501

# Set the entry point and command to run the Streamlit app
# We use Python as the entry point for running the Streamlit module
ENTRYPOINT ["streamlit", "run", "app.py"]

# Command line arguments for running the app on all interfaces
CMD ["--server.port", "8501", "--server.address", "0.0.0.0"]