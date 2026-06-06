# Runbook: Fixing Nginx 502 Bad Gateway Outages

**Ticket ID:** TCK-3312  
**Tier:** 4 (Critical Outage)

## Problem

Nginx 502 Bad Gateway outage on `web-ingress-01`.

## Root Cause

The upstream backend service daemon crashed unexpectedly due to an unhandled exception, leaving Nginx without a responsive socket connection.

## Resolution Summary

Inspect backend service health, restart the upstream service, then validate and reload Nginx.

## 1. Problem Statement

Users are receiving 502 Bad Gateway error pages when attempting to access the application through `web-ingress-01`.

## 2. Root Cause Analysis (RCA)

Nginx is functioning normally, but the upstream application service proxy socket is unavailable because the underlying application daemon crashed due to an unhandled runtime error.

## 3. Step-by-Step Resolution Actions

### Inspect Backend Daemon Health

```bash
sudo systemctl status backend-app-service
sudo journalctl -u backend-app-service -n 50 --no-pager
```

### Restart the Downed Upstream Daemon

```bash
sudo systemctl restart backend-app-service
```

### Verify and Reload Nginx

```bash
sudo nginx -t
sudo systemctl reload nginx
```