from locust import HttpUser, task, between

class TrailPeakUser(HttpUser):
    wait_time = between(1, 3)  # simulated pause between actions, like a real user

    @task(3)
    def ask_policy_question(self):
        self.client.post("/ask", json={"message": "What is your return policy?"})

    @task(1)
    def ask_product_question(self):
        self.client.post("/ask", json={"message": "Is the SummitCarry backpack in stock, and what does it cost?"})

    @task(1)
    def health_check(self):
        self.client.get("/health")