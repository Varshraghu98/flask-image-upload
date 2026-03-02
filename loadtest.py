import requests
import time
import statistics

BASE_URL = "http://localhost:5000"
TEST_DURATION = 120  # seconds
IMAGE_PATH = "test.jpg"

upload_latencies = []
download_latencies = []

start_time = time.perf_counter()
total_requests = 0
successful_cycles = 0

while time.perf_counter() - start_time < TEST_DURATION:

    # ---- Upload ----
    with open(IMAGE_PATH, "rb") as f:
        files = {"file": f}

        t1 = time.perf_counter()
        r = requests.post(
            BASE_URL + "/api/upload",
            files=files,
            timeout=10
        )
        upload_time = time.perf_counter() - t1

    if r.status_code != 201:
        continue

    upload_latencies.append(upload_time)

    try:
        image_id = r.json()["image_id"]
    except Exception:
        continue

    # ---- Download ----
    t2 = time.perf_counter()
    d = requests.get(
        BASE_URL + f"/api/images/{image_id}",
        timeout=10
    )
    download_time = time.perf_counter() - t2

    if d.status_code == 200:
        download_latencies.append(download_time)
        total_requests += 2
        successful_cycles += 1


# =============================
# Metrics Calculation
# =============================

def percentile(data, p):
    if not data:
        return 0
    return sorted(data)[int(len(data) * p / 100)]


print("\n==== RESULTS ====")
print(f"Successful Upload+Download Cycles: {successful_cycles}")
print(f"Total Requests: {total_requests}")
print(f"Test Duration: {TEST_DURATION} seconds")

if upload_latencies:
    print("\nUPLOAD LATENCY:")
    print(f"Avg: {statistics.mean(upload_latencies):.4f}s")
    print(f"Std Dev: {statistics.stdev(upload_latencies):.4f}s")
    print(f"P95: {percentile(upload_latencies, 95):.4f}s")
    print(f"P99: {percentile(upload_latencies, 99):.4f}s")

if download_latencies:
    print("\nDOWNLOAD LATENCY:")
    print(f"Avg: {statistics.mean(download_latencies):.4f}s")
    print(f"Std Dev: {statistics.stdev(download_latencies):.4f}s")
    print(f"P95: {percentile(download_latencies, 95):.4f}s")
    print(f"P99: {percentile(download_latencies, 99):.4f}s")

throughput = total_requests / TEST_DURATION
print(f"\nThroughput: {throughput:.2f} requests/sec")