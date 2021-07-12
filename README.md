# calendar-status-light
A light which quickly displays where I might be based on my calendar.

## Setup

### Local Development

To run this code locally (not on a RPi):

```shell
python3 app --mock_light
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

# Install a (reliable) network wait systemd gate.
cp systemd/network-wait-online.service /etc/systemd/system
systemctl enable network-wait-online.service

# Configure this to run at boot and start it.
cp systemd/calendar-status-light.service /etc/systemd/system
systemctl enable calendar-status-light.service

# Optional: Configure a daily update service.
cp systemd/calendar-status-light-update.service /etc/systemd/system
systemctl enable calendar-status-light-update.service

# Start everything.
systemctl start calendar-status-light.service
```
