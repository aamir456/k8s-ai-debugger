<#
.SYNOPSIS
  Break the demo-app in realistic ways, then debug it with Claude + kubernetes MCP.

.EXAMPLE
  .\scenarios\chaos.ps1 -List                 # show scenarios
  .\scenarios\chaos.ps1 -Scenario crashloop   # break something specific
  .\scenarios\chaos.ps1 -Random               # mystery break (doesn't tell you which)
  .\scenarios\chaos.ps1 -Status               # quick health view
  .\scenarios\chaos.ps1 -Reset                # restore the healthy baseline
#>
[CmdletBinding(DefaultParameterSetName = "List")]
param(
    [Parameter(ParameterSetName = "Break", Mandatory)]
    [ValidateSet("crashloop", "imagepull", "oom", "pending", "no-endpoints",
                 "redis-down", "bad-probe", "unready", "cpu-spike")]
    [string]$Scenario,
    [Parameter(ParameterSetName = "Random")] [switch]$Random,
    [Parameter(ParameterSetName = "Reset")]  [switch]$Reset,
    [Parameter(ParameterSetName = "Status")] [switch]$Status,
    [Parameter(ParameterSetName = "List")]   [switch]$List
)
$ErrorActionPreference = "Continue"
$Ctx = "kind-ai-debug"
$Ns = "demo-app"
$App = "http://localhost:8080"
$Base = Join-Path $PSScriptRoot "..\k8s\base"
$AnswerFile = Join-Path $HOME ".k8s-ai-debugger-last-scenario.txt"

function k { kubectl --context $Ctx -n $Ns @args }
function Send-Chaos([string]$path, [int]$times = 1) {
    1..$times | ForEach-Object {
        try { Invoke-RestMethod -Method Post "$App$path" -TimeoutSec 5 | Out-Null } catch { }
    }
}

# Every break only CHANGES fields that exist in k8s/base, so `-Reset`
# (kubectl apply + rollout restart) restores the baseline exactly.
$Scenarios = [ordered]@{
    "crashloop"    = @{ Title = "New release crashes on start"
                        Break = { k patch configmap notes-app-config --type merge -p '{\"data\":{\"REDIS_PORT\":\"six-three-seven-nine\"}}'
                                  k rollout restart deploy/notes-app } }
    "imagepull"    = @{ Title = "Deploy of a new version is stuck"
                        Break = { k set image deploy/notes-app notes-app=notes-app:1.1.0 } }
    "oom"          = @{ Title = "Pods keep restarting under load"
                        Break = { k patch deploy notes-app --type json -p '[{\"op\":\"replace\",\"path\":\"/spec/template/spec/containers/0/resources/limits/memory\",\"value\":\"100Mi\"}]'
                                  k rollout status deploy/notes-app --timeout=120s | Out-Null
                                  Send-Chaos "/chaos/leak?mb=25" 12 } }
    "pending"      = @{ Title = "Rollout never finishes"
                        Break = { k patch deploy notes-app --type json -p '[{\"op\":\"replace\",\"path\":\"/spec/template/spec/nodeSelector/tier\",\"value\":\"gpu\"}]' } }
    "no-endpoints" = @{ Title = "Website returns errors but all pods look healthy"
                        Break = { k patch service notes-app --type json -p '[{\"op\":\"replace\",\"path\":\"/spec/selector/app.kubernetes.io~1name\",\"value\":\"notes\"}]' } }
    "redis-down"   = @{ Title = "Website down, pods running but not ready"
                        Break = { k scale statefulset redis --replicas=0 } }
    "bad-probe"    = @{ Title = "Restart count keeps climbing"
                        Break = { k patch deploy notes-app --type json -p '[{\"op\":\"replace\",\"path\":\"/spec/template/spec/containers/0/livenessProbe/httpGet/path\",\"value\":\"/health\"}]' } }
    "unready"      = @{ Title = "Capacity reduced, one pod not serving"
                        Break = { Send-Chaos "/chaos/unready" 1 } }
    "cpu-spike"    = @{ Title = "Pod count jumped unexpectedly"
                        Break = { Send-Chaos "/chaos/cpu?seconds=300" 4 } }
}

function Show-Status {
    Write-Host "`n== Pods ==" -ForegroundColor Cyan
    k get pods -o wide
    Write-Host "`n== Deployment / HPA / Endpoints ==" -ForegroundColor Cyan
    k get "deploy,sts,hpa"
    k get endpointslices -l kubernetes.io/service-name=notes-app
    Write-Host "`n== Website ==" -ForegroundColor Cyan
    try { $r = Invoke-WebRequest -UseBasicParsing "$App/readyz" -TimeoutSec 5; "HTTP $($r.StatusCode) $($r.Content)" }
    catch { "HTTP error: $($_.Exception.Message)" }
}

switch ($PSCmdlet.ParameterSetName) {
    "List" {
        Write-Host "Scenarios (symptom you would get as an on-call engineer):`n"
        $Scenarios.GetEnumerator() | ForEach-Object { "  {0,-13} {1}" -f $_.Key, $_.Value.Title }
        Write-Host "`nUse -Scenario <name>, -Random, -Status or -Reset."
    }
    "Status" { Show-Status }
    "Reset" {
        Write-Host "Restoring baseline from k8s/base ..." -ForegroundColor Yellow
        k apply -k $Base | Out-Null
        k rollout restart deploy/notes-app | Out-Null      # clears leaks, CPU burners, forced-unready
        k rollout status statefulset/redis --timeout=180s
        k rollout status deploy/notes-app --timeout=180s
        Remove-Item $AnswerFile -ErrorAction SilentlyContinue
        Show-Status
    }
    { $_ -in "Break", "Random" } {
        if ($Random) { $Scenario = Get-Random -InputObject @($Scenarios.Keys) }
        $s = $Scenarios[$Scenario]
        & $s.Break 2>&1 | Out-Null
        Set-Content -Path $AnswerFile -Value $Scenario
        if ($Random) {
            Write-Host "Something broke in namespace $Ns. Ask Claude to investigate!" -ForegroundColor Red
            Write-Host "(Answer saved to $AnswerFile - don't peek.)"
        } else {
            Write-Host "Broke: $Scenario - symptom: $($s.Title)" -ForegroundColor Red
        }
        Write-Host "Give it ~30-60 seconds for symptoms to appear, then debug. Reset with: .\scenarios\chaos.ps1 -Reset"
    }
}
