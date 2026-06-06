# Runbook: Resolving PostgreSQL Performance Degradation

**Ticket ID:** TCK-5520  
**Tier:** 3 (Performance Degradation)

## Problem

PostgreSQL high CPU utilization and slow query latency on `order-db-prod`.

## Root Cause

Missing database indexes on frequently queried columns in the `orders` table during high-volume checkout scans.

## Resolution Summary

Identify slow queries using `pg_stat_statements`, create a composite index, and update table statistics.

## 1. Problem Statement

Production monitoring alerts indicate database response times on `order-db-prod` have exceeded the 2000ms threshold, causing high checkout latency.

## 2. Root Cause Analysis (RCA)

Sequential scans are occurring on the `orders` table due to a missing composite index on `user_id` and `status`, forcing the database engine to consume excessive CPU resources.

## 3. Step-by-Step Resolution Actions

### Identify Top Slow Queries

```sql
SELECT query, calls, total_exec_time
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 5;
```

### Apply Index Non-Blockingly

```sql
CREATE INDEX CONCURRENTLY idx_orders_user_status
ON orders(user_id, status);
```

### Update Table Statistics

```sql
ANALYZE orders;
```