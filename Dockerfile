# Grab Ubuntu.
FROM ubuntu:latest

# Install.
RUN \
  sed -i 's/# \(.*multiverse$\)/\1/g' /etc/apt/sources.list && \
  apt-get update && \
  apt-get -y upgrade && \
  apt-get install -y build-essential && \
  apt-get install -y python3-dev python3 python3-pip && \
  rm -rf /var/lib/apt/lists/*

# Set environment variables.
ENV HOME /usr/src/app

# Setup the running location of the container and the python requirements.
WORKDIR /usr/src/app

# Get required modules.
ENV PYTHONWARNINGS "ignore:Unverified HTTPS request"
COPY requirements.txt requirements.txt
RUN pip3 install --trusted-host pypi.python.org -r requirements.txt

# Declare open ports.
EXPOSE 80 8080

# Copy everything from here to the container.
COPY app.py .

# Not running on an RPi, use mock out gpiozero.
ENV GPIOZERO_PIN_FACTORY mock

# Start the application.
ENTRYPOINT ["python3", "app.py"]
CMD []
