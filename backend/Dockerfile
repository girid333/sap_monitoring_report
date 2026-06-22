FROM python:3.11-slim

# Install system dependencies required for pyrfc and building packages
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# The user must provide the nwrfcsdk folder in the backend directory.
# We copy it to the standard SAP local path.
COPY nwrfcsdk /usr/local/sap/nwrfcsdk

# Set the environment variables required by pyrfc and the SAP SDK
ENV SAPNWRFC_HOME="/usr/local/sap/nwrfcsdk"
ENV LD_LIBRARY_PATH="/usr/local/sap/nwrfcsdk/lib"
ENV PATH="$PATH:/usr/local/sap/nwrfcsdk/lib"

# To ensure the dynamic linker knows where the library is:
RUN echo "/usr/local/sap/nwrfcsdk/lib" > /etc/ld.so.conf.d/nwrfcsdk.conf && ldconfig

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Run the backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
