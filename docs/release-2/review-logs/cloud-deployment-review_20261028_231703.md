# Cloud Deployment Review

**Agent recommendation:** CONDITIONAL · **Human release decision:** CONDCOCONDITIONAOL · **Generated:** 2026-10-28 23:17

| Stage | Detail |
| --- | --- |
| Plan | Review the Azure deployment in resource group 'group29-r2-rg': app inventory, frontend reachability, AI services disabled by default, Student 2 CRUD, then record the human release decision. |
| Act | Found 9 Container App(s) via az containerapp list -g group29-r2-rg; probing every external frontend over HTTPS. |
| Observe | 4/5 frontend(s) responded; 4/4 behaviour check(s) passed. |
| Adapt | Agent recommendation: CONDITIONAL with 1 risk(s). |
| Adapt | Human release decision: CONDCOCONDITIONAOL -- conditional |

## Container App inventory (az containerapp list -g group29-r2-rg)

| App | Status | URL |
| --- | --- | --- |
| group29cc-home | - | https://group29cc-home.livelydesert-b33495c0.eastasia.azurecontainerapps.io |
| student-4-backend | Running | https://student-4-backend.livelydesert-b33495c0.eastasia.azurecontainerapps.io |
| student-2-backend | Running | https://student-2-backend.livelydesert-b33495c0.eastasia.azurecontainerapps.io |
| student-3-backend | Running | https://student-3-backend.livelydesert-b33495c0.eastasia.azurecontainerapps.io |
| student-1-backend | Running | https://student-1-backend.livelydesert-b33495c0.eastasia.azurecontainerapps.io |
| student-4-frontend | Running | https://student-4-frontend.livelydesert-b33495c0.eastasia.azurecontainerapps.io |
| student-2-frontend | Running | https://student-2-frontend.livelydesert-b33495c0.eastasia.azurecontainerapps.io |
| student-3-frontend | Running | https://student-3-frontend.livelydesert-b33495c0.eastasia.azurecontainerapps.io |
| student-1-frontend | Running | https://student-1-frontend.livelydesert-b33495c0.eastasia.azurecontainerapps.io |

## Frontend reachability

| App | HTTP | First response | Result |
| --- | --- | --- | --- |
| group29cc-home | 503 | 749 ms | FAIL |
| student-4-frontend | 200 | 1266 ms | OK |
| student-2-frontend | 200 | 1903 ms | OK |
| student-3-frontend | 200 | 1252 ms | OK |
| student-1-frontend | 200 | 1462 ms | OK |

## Behaviour checks (Student 2)

| Check | Result |
| --- | --- |
| Multi-Agent disabled in cloud | PASS |
| MCP disabled in cloud | PASS |
| CRUD create (open position) | PASS |
| CRUD delete (close position) | PASS |

## Risks
- Non-student apps not responding: group29cc-home.

## Human release decision
**CONDCOCONDITIONAOL** -- conditional
