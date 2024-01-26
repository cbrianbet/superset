# Base image
FROM python:3.9-slim

#Specifying timezone
ENV TZ=Africa/Nairobi

# Install cron and git
RUN apt-get update && apt-get install -y cron git

# Set the working directory
WORKDIR /app

# Copy the requirements file
COPY requirements.txt .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Expose the port
EXPOSE 8000

# Copy the cron script
#COPY cron_script.sh /app

# Set execution permissions for the cron script
#RUN chmod +x /app/cron_script.sh

# Command to run the application and start the cron job
CMD uvicorn app:app --host 0.0.0.0 --port 8000
