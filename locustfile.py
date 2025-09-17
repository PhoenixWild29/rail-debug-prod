from locust import HttpUser, task

class RailDebugUser(HttpUser):
    @task
    def debug_rail_code(self):
        self.client.post("/debug-rail-code", json={
            "query": "Why does this rail code fail?",
            "few_shot_examples": [{"input": "Sensor error", "output": "Check sensor wiring."}],
            "docs": ["Rail sensor code guide."]
        })

# Run with: locust -f locustfile.py --host http://localhost:8000