
# Use an official Python runtime as a parent image
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble@sha256:640d578aae63cfb632461d1b0aecb01414e4e020864ac3dd45a868dc0eff3078

# Set the working directory in the container
WORKDIR /app

# Install git and ffmpeg
RUN apt-get update && apt-get install -y git ffmpeg fonts-dejavu-core

# Use existing user with UID 1000 from base image (pwuser)
# The base Playwright image already has a user with UID 1000

# Copy the requirements file first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source code
COPY ./src /app/src
COPY run_workers.py entrypoint.sh /app/

# Make the entrypoint script executable
RUN chmod +x /app/entrypoint.sh

# Change ownership of /app to user 1000 (pwuser from base image)
RUN chown -R 1000:1000 /app

# Switch to non-root user (UID 1000)
USER 1000

# Expose the port the app runs on
EXPOSE 8000

# Set the entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command to run the web server
CMD ["web"]
