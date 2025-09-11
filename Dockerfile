
# Use an official Python runtime as a parent image
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

# Set the working directory in the container
WORKDIR /app

# Install git and ffmpeg
RUN apt-get update && apt-get install -y git ffmpeg fonts-dejavu-core

# Copy the requirements file first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source code
COPY ./src /app/src
COPY run_workers.py entrypoint.sh /app/

# Make the entrypoint script executable
RUN chmod +x /app/entrypoint.sh

# Expose the port the app runs on
EXPOSE 8000

# Set the entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command to run the web server
CMD ["web"]
