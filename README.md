# SMS Service

A Python service for Grandstream UCM IP PBX systems.

This project monitors CDR records from a Grandstream UCM system and sends SMS automatically when specific call conditions are detected.

## Features
- Reads call records from CDR API
- Detects new calls
- Sends SMS automatically
- Writes logs to file
- Can run as a systemd service
- Can be monitored with ELK Stack

## Requirements
- Ubuntu Linux
- Python 3.12
- pip
- systemd
- Docker and Docker Compose (for ELK)

## Project Structure
```bash
smk-project/
│
├── server.py
├── README.md
├── requirements.txt
├── .gitignore
│
├── log/
│   └── .gitkeep
│
├── systemd/
│   └── smk.service
│
└── elk/
    ├── docker-compose.yml
    └── filebeat.yml
```

## Installation

sudo apt update
sudo apt install python3.12-venv -y

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

## Configuration

Edit `server.py` and configure:

- CDR_URL
- CDR_USER
- CDR_PASS
- SMS_URL
- SMS_USER
- SMS_PASS
- SENDER

## Run

```bash
source venv/bin/activate
python3 server.py
```

## Run as a Service

```bash
sudo cp systemd/smk.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sms
sudo systemctl start sms
sudo systemctl status sms
```

## ELK Monitoring

Start Elasticsearch, Kibana and Filebeat.

```bash
cd ELK
docker compose up -d
```

Kibana:

```
http://SERVER_IP:5601
```

## Logs

Application log:

```bash
tail -f log/smk.log
```

## Workflow

```
Incoming Call
      │
      ▼
   CDR API
      │
      ▼
 Python Service
      │
 ├── Send SMS
 └── Write Log
          │
          ▼
      Filebeat
          │
          ▼
   Elasticsearch
          │
          ▼
       Kibana
```
