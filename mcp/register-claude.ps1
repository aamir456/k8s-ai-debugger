<#
.SYNOPSIS
  Writes .mcp.json in the repository root so Claude Code starts the read-only
  kubernetes-mcp-server container when you open a session in this folder.

.DESCRIPTION
  Docker bind mounts need absolute paths, so .mcp.json is generated per machine
  (and git-ignored). Run new-mcp-kubeconfig.ps1 first.

.EXAMPLE
  .\mcp\register-claude.ps1
  .\mcp\register-claude.ps1 -Target ..        # write it into a parent folder instead
#>
param(
    [string]$Target = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$Kubeconfig = "$HOME\.kube\mcp-viewer.docker.kubeconfig"
)
$ErrorActionPreference = "Stop"
$Image = "quay.io/containers/kubernetes_mcp_server@sha256:200c1aba3b47b9ab572f61d64f689f63f5abccab3e5e95b4aee34c7411658ad3"
$Config = (Resolve-Path (Join-Path $PSScriptRoot "config.toml")).Path

if (-not (Test-Path $Kubeconfig)) {
    throw "Missing $Kubeconfig - run .\mcp\new-mcp-kubeconfig.ps1 first."
}

$mcp = [ordered]@{
    mcpServers = [ordered]@{
        kubernetes = [ordered]@{
            type    = "stdio"
            command = "docker"
            args    = @(
                "run", "-i", "--rm", "--network", "kind",
                "-v", "${Kubeconfig}:/etc/kubernetes-mcp-server/kubeconfig:ro",
                "-v", "${Config}:/etc/kubernetes-mcp-server/config.toml:ro",
                $Image,
                "--config", "/etc/kubernetes-mcp-server/config.toml"
            )
        }
    }
}
$out = Join-Path $Target ".mcp.json"
$mcp | ConvertTo-Json -Depth 5 | Set-Content -Path $out -Encoding utf8
Write-Host "Wrote $out"
Write-Host "Start a NEW Claude Code session in $Target and approve the 'kubernetes' MCP server."
