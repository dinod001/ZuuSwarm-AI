# Runbook: Redis Out of Memory (OOM) Mitigation

**Ticket ID:** TCK-8841  
**Tier:** 4 (Critical Outage)

## Problem

Redis Out of Memory (OOM) crash on `prod-cache-01`.

## Root Cause

Eviction policy misconfiguration causing memory leak because old keys remain cached indefinitely without being evicted.

## Resolution Summary

Flush the current cache and update the Redis eviction policy to `allkeys-lru`, then restart Redis.

## 1. Problem Statement

The Redis caching instance on `prod-cache-01` has hit its maximum memory limit, causing severe API drops and explicit OOM errors during peak hours.

## 2. Root Cause Analysis (RCA)

Investigation shows that the `maxmemory-policy` in Redis configuration was set incorrectly, disabling automated key eviction. Volatile keys accumulated indefinitely, leading to an artificial memory leak.

## 3. Step-by-Step Resolution Actions

### Immediate Cache Clearing

```bash
redis-cli -h prod-cache-01 FLUSHALL
```

### Configuration Update

Open:

```text
/etc/redis/redis.conf
```

Update or append:

```text
maxmemory-policy allkeys-lru
```

### Service Restart

```bash
sudo systemctl restart redis-server
```