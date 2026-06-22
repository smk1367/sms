# SMK SMS Service

This project monitors CDR logs and sends SMS automatically when a target call pattern is detected.

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
├── server.py
├── requirements.txt
├── README.md
├── .gitignore
├── log/
├── systemd/
└── elk/
