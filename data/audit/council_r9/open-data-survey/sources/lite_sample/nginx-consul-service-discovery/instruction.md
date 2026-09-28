## Dynamic Reverse Proxy with Service Discovery

Set up an Nginx reverse proxy that dynamically discovers and routes traffic to backend services using Consul for DNS-based service discovery.

### Technical Requirements

- **OS:** Ubuntu/Debian-based system
- **Components:** Nginx, Consul (agent in dev mode), Python 3 (for backend services)
- **Working directory:** /app

### Infrastructure Setup

1. **Consul Agent**
   - Run Consul in dev mode, listening on `127.0.0.1`.
   - DNS interface on port `8600`, HTTP API on port `8500`.

2. **Backend Services**
   - Create three simple HTTP backend services using Python. Each service returns a JSON response `{"service": "<name>", "port": <port>}` on any HTTP GET request.
     - `web-api` on port `8001`
     - `web-api` on port `8002`
     - `web-api` on port `8003`
   - Each service must be registered in Consul with:
     - Service name: `web-api`
     - A unique service ID per instance (e.g., `web-api-1`, `web-api-2`, `web-api-3`)
     - An HTTP health check that hits the service's root endpoint every 5 seconds.

3. **Nginx Configuration**
   - Nginx listens on port `80`.
   - Use Consul's DNS interface (`127.0.0.1:8600`) as the resolver with `valid=5s`.
   - Define a location block at `/api/` that proxies requests to the backend services discovered via Consul DNS. The upstream host should be resolved using the Consul DNS name for the `web-api` service (i.e., `web-api.service.consul`).
   - Enable proxy headers: `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, `Host`.

### File Structure

```
/app/
├── nginx/
│   └── nginx.conf              # Full Nginx configuration
├── consul/
│   └── web-api.json            # Consul service definition file for all three instances
├── services/
│   ├── backend.py              # Python HTTP backend service (accepts --port argument)
│   └── start_services.sh       # Script to start all three backend instances in background
├── test.sh                     # Test script (described below)
└── output.json                 # Test results output
```

### Service Registration

The file `/app/consul/web-api.json` must be a valid JSON file that defines the three service instances for Consul registration. Each service entry must include `Name`, `ID`, `Port`, and a `Check` with an HTTP health check.

### Test Script (`/app/test.sh`)

Create an executable bash script at `/app/test.sh` that:

1. Verifies Consul is running and healthy (HTTP API at `http://127.0.0.1:8500/v1/status/leader` returns a non-empty response).
2. Verifies all three backend services are running and responding on ports 8001, 8002, 8003.
3. Queries Consul's service catalog (`http://127.0.0.1:8500/v1/catalog/service/web-api`) and confirms 3 instances are registered.
4. Sends 6 HTTP requests to `http://localhost/api/` via Nginx and collects the responses.
5. Verifies that Nginx successfully proxied requests (i.e., received valid JSON responses from backends).

Write results to `/app/output.json` in this exact format:

```json
{
  "consul_running": true,
  "backends_healthy": true,
  "registered_services_count": 3,
  "nginx_proxy_success": true,
  "total_requests": 6,
  "successful_responses": 6
}
```

- `consul_running`: true if Consul's leader endpoint returns a valid response.
- `backends_healthy`: true if all three ports (8001, 8002, 8003) respond to HTTP GET.
- `registered_services_count`: integer count of `web-api` services in Consul catalog.
- `nginx_proxy_success`: true if all 6 requests through Nginx returned valid JSON with a `service` key.
- `total_requests`: always 6.
- `successful_responses`: count of requests that returned HTTP 200 with valid JSON.

### Constraints

- All backend services must be running as background processes.
- Nginx must be running and serving on port 80.
- Consul must be running in dev mode.
- The test script must be executable (`chmod +x /app/test.sh`) and produce `/app/output.json` when run.
