# calendar-status-light
A light which quickly displays where I might be based on my calendar.

## Setup

Do the following to prepare the RPi Zero W:

```shell
# Get a version of Docker compatible with the RPi Zero W.
# https://github.com/moby/moby/issues/38175#issuecomment-437681349
$ apt-get install docker-ce=18.06.1~ce~3-0~raspbian
$ systemctl enable docker.service
$ systemctl start docker.service

# Get the Docker local-persist plugin.
# https://github.com/MatchbookLab/local-persist#running-outside-a-container
$ curl -fsSL https://raw.githubusercontent.com/CWSpear/local-persist/master/scripts/install.sh \
  | sudo bash

# Build this container.
$ docker build -t calendar-status-light .

# Configure this container to run at boot and start it.
$ cp systemctl/calendar-status-light.service /etc/systemd/system
$ systemctl enable calendar-status-light.service
$ systemctl start calendar-status-light.service
```
