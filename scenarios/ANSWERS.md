# Answer Key (spoilers!)

What each scenario changes, the evidence the MCP tools should surface, and the fix.
`-Reset` fixes all of them.

## crashloop — bad configuration
- **Change:** ConfigMap `notes-app-config` key `REDIS_PORT` = `six-three-seven-nine`, then rollout restart.
- **Evidence:** new pod `CrashLoopBackOff`; `pods_log` (previous=true) shows
  `ValueError: invalid literal for int() with base 10: 'six-three-seven-nine'`.
  Old pods keep serving because `maxUnavailable: 0` — the rollout is stuck, not an outage.
- **Fix:** set `REDIS_PORT: "6379"` in the ConfigMap, then `kubectl -n demo-app rollout restart deploy/notes-app`.

## imagepull — image doesn't exist
- **Change:** image set to `notes-app:1.1.0` (never built / loaded into kind).
- **Evidence:** new pod `ErrImagePull` / `ImagePullBackOff`; `events_list` shows
  pull failure for `docker.io/library/notes-app:1.1.0`.
- **Fix:** `kubectl -n demo-app rollout undo deploy/notes-app`, or build + `kind load` the tag.

## oom — memory limit too low
- **Change:** memory limit lowered to `100Mi`; `/chaos/leak` grows memory.
- **Evidence:** restarts > 0; `pods_get` shows `lastState.terminated.reason: OOMKilled`,
  exit code 137; `pods_top` shows memory approaching the limit.
- **Fix:** restore limit `256Mi` (and in real life: find the leak — the `chaos_leaked_megabytes` metric).

## pending — unschedulable
- **Change:** `nodeSelector` `tier: gpu` — no node has that label.
- **Evidence:** pod `Pending`; event `FailedScheduling ... didn't match Pod's node affinity/selector`;
  `resources_list` Nodes shows labels `tier=app` only.
- **Fix:** set `nodeSelector.tier: app` (or label a node, `kubectl label node ai-debug-worker tier=gpu`).

## no-endpoints — Service selector mismatch
- **Change:** Service `notes-app` selector `app.kubernetes.io/name: notes` (pods are labelled `notes-app`).
- **Evidence:** all pods Running/Ready, but EndpointSlice for `notes-app` has no endpoints;
  website returns 503 (Envoy has no upstream).
- **Fix:** restore the selector `app.kubernetes.io/name: notes-app`.

## redis-down — dependency outage
- **Change:** StatefulSet `redis` scaled to 0.
- **Evidence:** no `redis-0` pod; app pods `0/1` Ready; events `Readiness probe failed: HTTP 503`;
  `pods_log` shows `readiness failed: redis unreachable`.
- **Fix:** `kubectl -n demo-app scale statefulset redis --replicas=1`.

## bad-probe — wrong liveness path
- **Change:** livenessProbe path `/health` (app serves `/healthz`).
- **Evidence:** restarts climbing every ~30-40 s; events `Liveness probe failed: HTTP probe failed
  with statuscode: 404` then `Killing ... failed liveness probe`; logs show `GET /health 404`.
- **Fix:** set the liveness path back to `/healthz`.

## unready — one pod failing readiness
- **Change:** `/chaos/unready` toggled on one pod.
- **Evidence:** one pod `0/1`; its `/readyz` returns 503 `forced via /chaos/unready`; that pod is
  missing from the EndpointSlice; Redis is fine (other pod Ready).
- **Fix:** `kubectl -n demo-app delete pod <that pod>` (or POST `/chaos/unready` again).

## cpu-spike — autoscaling
- **Change:** `/chaos/cpu` burns CPU for 5 minutes on pods.
- **Evidence:** HPA `notes-app` at ~500% CPU of target 70%, replicas scaled to 6 (max);
  `pods_top` shows ~500m CPU on affected pods; logs `chaos: burning CPU`.
- **Fix:** nothing is broken — HPA worked as designed. Pods scale back down ~5 min after the load stops.
  Investigate the source of load; consider `maxReplicas` / CPU limits.
