<#
.SYNOPSIS
  Builds a kubeconfig for kubernetes-mcp-server that contains ONLY the kind
  cluster and the read-only mcp-viewer ServiceAccount token.

.DESCRIPTION
  Re-run this when:
    - the token expires (default 30 days), or
    - the kind cluster is recreated (API port and CA change).
  The file is written outside the project so the token is never committed.

.EXAMPLE
  .\mcp\new-mcp-kubeconfig.ps1
#>
param(
    [string]$Context = "kind-ai-debug",
    [string]$Duration = "720h",
    [string]$OutFile = "$HOME\.kube\mcp-viewer.kubeconfig",
    # The MCP server runs in a container on the `kind` Docker network, where the
    # API server is reachable by the control-plane container name.
    [string]$InternalServer = "https://ai-debug-control-plane:6443",
    [string]$DockerOutFile = "$HOME\.kube\mcp-viewer.docker.kubeconfig"
)
$ErrorActionPreference = "Stop"

# Make sure the ServiceAccount + RBAC exist
kubectl --context $Context apply -f "$PSScriptRoot\rbac-readonly.yaml" | Out-Null

# Cluster details from the admin context
$server = kubectl config view --raw -o jsonpath="{.clusters[?(@.name=='$Context')].cluster.server}"
$caData = kubectl config view --raw -o jsonpath="{.clusters[?(@.name=='$Context')].cluster.certificate-authority-data}"
if (-not $server -or -not $caData) { throw "Context '$Context' not found in your kubeconfig." }

# Short-lived, bound ServiceAccount token
$token = kubectl --context $Context -n mcp create token mcp-viewer --duration $Duration
if (-not $token) { throw "Could not create a token for mcp/mcp-viewer." }

$template = @"
apiVersion: v1
kind: Config
clusters:
  - name: ai-debug
    cluster:
      server: __SERVER__
      certificate-authority-data: $caData
users:
  - name: mcp-viewer
    user:
      token: $token
contexts:
  - name: ai-debug-mcp-viewer
    context:
      cluster: ai-debug
      user: mcp-viewer
      namespace: demo-app
current-context: ai-debug-mcp-viewer
"@
New-Item -ItemType Directory -Force (Split-Path $OutFile) | Out-Null
# Host copy (for kubectl on Windows) and container copy (for the MCP server)
Set-Content -Path $OutFile -Value $template.Replace("__SERVER__", $server) -Encoding ascii -NoNewline
Set-Content -Path $DockerOutFile -Value $template.Replace("__SERVER__", $InternalServer) -Encoding ascii -NoNewline

# Sanity check: should list pods, and must NOT be able to read secrets
Write-Host "Kubeconfig written to $OutFile and $DockerOutFile (token valid for $Duration)"
kubectl --kubeconfig $OutFile get pods -n demo-app
$secrets = kubectl --kubeconfig $OutFile auth can-i get secrets -n demo-app 2>$null
Write-Host "Can read secrets: $secrets (expected: no)"
