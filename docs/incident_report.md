# Incident report: release v2.3.1

Log: `incident.log`. Deploy at 2026-03-02 14:20:00 UTC.
Compared the 15 minutes before the deploy with the 15 minutes after.
An error type is flagged when it has at least 10 errors after the deploy and is either new or at least 3x its count before.

Errors in the window: 10 before, 50 after. Malformed lines skipped: 0.

## Findings

| Service | Error type | Before | After | Change |
|---|---|---|---|---|
| checkout-service | UpstreamFailure | 3 | 23 | 7.7x |
| payment-service | TimeoutError | 3 | 23 | 7.7x |

## Likely root cause

checkout-service UpstreamFailure: 23 affected requests.
- 23 of 23 (100%) first failed in payment-service with TimeoutError.

payment-service TimeoutError: 23 affected requests.
- 23 of 23 (100%) first failed in payment-service with TimeoutError.

## Example trace: req-00302

```
14:20:16 INFO  checkout-service  order received
14:20:16 INFO  payment-service   charge started
14:20:17 ERROR payment-service   upstream timed out after 5000ms
14:20:18 ERROR checkout-service  payment call failed
```
