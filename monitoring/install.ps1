<#
.SYNOPSIS
  Installs kube-prometheus-stack (Prometheus, Alertmanager, Grafana, kube-state-metrics,
  node-exporter) plus the notes-app PodMonitor, alerts and dashboard.

.DESCRIPTION
  Helm runs inside a pinned container on the "kind" Docker network because Windows
  Smart App Control blocks the native helm.exe. Safe to re-run (helm upgrade --install).

.EXAMPLE
  .\monitoring\install.ps1
#>
param(
    [string]$Context = "kind-ai-debug",
    [string]$ClusterName = "ai-debug",
    [string]$ChartVersion = "93.6.1"
)
$ErrorActionPreference = "Stop"
$HelmImage = "alpine/helm@sha256:a3b9d617c0c30a6c488cebb429c4ba83995a26dc2184599af5fd408a361b2e67"  # helm v4.3.2
$Here = $PSScriptRoot

# 1. Namespace + Grafana admin secret with a random password (created once)
kubectl --context $Context create namespace monitoring --dry-run=client -o yaml | kubectl --context $Context apply -f - | Out-Null
$existing = kubectl --context $Context -n monitoring get secret grafana-admin --ignore-not-found -o name
if (-not $existing) {
    $pw = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    kubectl --context $Context -n monitoring create secret generic grafana-admin `
        --from-literal=admin-user=admin --from-literal=admin-password=$pw | Out-Null
    Write-Host "Created Grafana admin secret (user: admin)."
}

# 2. Admin kubeconfig that works from inside the kind Docker network (temp file, deleted after)
$kc = Join-Path $env:TEMP "kind-$ClusterName-internal.kubeconfig"
kind get kubeconfig --internal --name $ClusterName | Set-Content -Encoding ascii $kc
try {
    docker run --rm --network kind `
        -v "${kc}:/root/.kube/config:ro" `
        -v "${Here}:/work:ro" `
        $HelmImage upgrade --install kps kube-prometheus-stack `
        --repo https://prometheus-community.github.io/helm-charts `
        --version $ChartVersion `
        --namespace monitoring `
        -f /work/values.yaml `
        --wait --timeout 10m
    if ($LASTEXITCODE -ne 0) { throw "helm install failed" }
} finally {
    Remove-Item $kc -ErrorAction SilentlyContinue
}

# 3. App monitoring (needs the CRDs installed above)
kubectl --context $Context apply -k (Join-Path $Here "app")

Write-Host "`nGrafana:      http://grafana.localhost:8080   (user admin)"
Write-Host "Prometheus:   http://prometheus.localhost:8080"
Write-Host "Alertmanager: http://alertmanager.localhost:8080"
Write-Host "Grafana password:"
Write-Host '  kubectl -n monitoring get secret grafana-admin -o jsonpath="{.data.admin-password}" | % { [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($_)) }'
