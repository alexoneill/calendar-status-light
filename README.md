# calendar-status-light
A light which quickly displays where I might be based on my calendar.

## Setup

### Local Development

To run this code locally (not on a RPi), use `docker`:

```shell
docker build -t calendar-status-light .

# Save the Google OAuth2.0 creds somewhere special.
mkdir -p /tmp/calendar-status-light

# Run the container.
docker run --rm -it -v /tmp/calendar-status-light:/usr/src/app/secret \
  calendar-status-light:latest
```

### RPi Zero W

Do the following to prepare the RPi Zero W:

```shell
# Authenticate as root.
sudo su

# Clone the repo into /root.
cd /root
git clone ... calendar-status-light

# Ensure that python3 is installed.
apt-get install python3 python3-pip

# Install requisite packages.
export PYTHONWARNINGS="ignore:Unverified HTTPS request"
pip3 install --trusted-host pypi.python.org -r requirements.txt

# Save the OAuth2.0 creds from Google in ./secret/
mkdir -p secret

# Run the app once to authenticate.
python3 app.py --auth_only

# Configure this to run at boot and start it.
cp systemd/calendar-status-light.service /etc/systemd/system
systemctl enable calendar-status-light.service
systemctl start calendar-status-light.service
```
