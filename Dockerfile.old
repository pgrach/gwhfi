# Use official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the ingestion folder and requirements
COPY ingestion/ ./ingestion/

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r ingestion/requirements.txt

# Copy the startup script
COPY start.sh .
RUN chmod +x start.sh

# Environment variables will be injected by Railway
# CMD to run the startup script
CMD ["./start.sh"]
