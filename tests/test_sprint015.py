import pytest
import subprocess
import time
import requests
import os
import sys

# Use docker compose v2 syntax
COMPOSE_CMD = ["docker", "compose"]

DEMO_TRACEBACK = '''Traceback (most recent call last):
  File "app.py", line 42, in <module>
    x = 1 / 0
ZeroDivisionError: division by zero'''

DEMO_CHAINED = '''Traceback (most recent call last):
  File "db/connection.py", line 23, in connect
    conn = psycopg2.connect(host=db_host, port=5432)
psycopg2.OperationalError: connection refused

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "api/routes.py", line 45, in get_user
    user = db.fetch_user(user_id)
DatabaseError: Failed to fetch user'''

@pytest.fixture(scope="module")
def docker_services():
    """Spin up docker-compose services."""
    subprocess.run([*COMPOSE_CMD, "up", "-d", "--build", "--wait"], check=True, cwd=repo_dir())
    time.sleep(5)  # extra wait
    yield
    subprocess.run([*COMPOSE_CMD, "down", "-v"], check=True, cwd=repo_dir())

def repo_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def test_docker_build():
    """Test Dockerfile builds."""
    result = subprocess.run(["docker", "build", "-t", "rail-debug-test", "."], 
                            cwd=repo_dir(), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

def test_server_health(docker_services):
    r = requests.get("http://localhost:8000/health", timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_analyze_single(docker_services):
    r = requests.post("http://localhost:8000/analyze", 
                      json={"traceback": DEMO_TRACEBACK}, timeout=60)
    assert r.status_code == 200
    data = r.json()
    assert "severity" in data
    assert data["error_type"] == "ZeroDivisionError"
    assert data["root_cause"]

def test_analyze_chain(docker_services):
    r = requests.post("http://localhost:8000/analyze/chain", 
                      json={"traceback": DEMO_CHAINED}, timeout=60)
    assert r.status_code == 200
    data = r.json()
    assert "reports" in data
    assert len(data["reports"]) >= 1