#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Deploy Lambda code directly to AWS without full CDK deploy.
.DESCRIPTION
  Zips each backend Lambda folder and updates the function code via AWS CLI.
  Requires: AWS CLI configured, TranslationService stack already deployed.
.EXAMPLE
  .\scripts\deploy-lambdas-direct.ps1
  .\scripts\deploy-lambdas-direct.ps1 -Region us-west-2
#>

param(
  [string]$Region = "us-west-2",
  [string]$StackPrefix = "TranslationService"
)

$ErrorActionPreference = "Stop"
$BackendRoot = Join-Path $PSScriptRoot "..\backend"

# Map folder name -> CDK logical ID substring (used to find Lambda by name)
$Lambdas = @(
  @{ Folder = "upload_proxy";      Pattern = "UploadProxy" }
  @{ Folder = "presigned_url";     Pattern = "PresignedUrlHandler" }
  @{ Folder = "translate_trigger"; Pattern = "TranslateTrigger" }
  @{ Folder = "notification_handler"; Pattern = "NotificationHandler" }
  @{ Folder = "status_handler";    Pattern = "StatusHandler" }
)

$TempDir = Join-Path $env:TEMP "pdf-poly-lingo-lambda-deploy"
if (-not (Test-Path $TempDir)) { New-Item -ItemType Directory -Path $TempDir | Out-Null }

Write-Host "Deploying Lambda code to region: $Region" -ForegroundColor Cyan
Write-Host ""

foreach ($lambda in $Lambdas) {
  $folder = $lambda.Folder
  $pattern = $lambda.Pattern
  $srcPath = Join-Path $BackendRoot $folder
  $zipPath = Join-Path $TempDir "$folder.zip"

  if (-not (Test-Path $srcPath)) {
    Write-Host "  [SKIP] $folder - source not found" -ForegroundColor Yellow
    continue
  }

  Write-Host "  Zipping $folder..." -NoNewline
  $zipFullPath = Resolve-Path $zipPath -ErrorAction SilentlyContinue
  Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
  Compress-Archive -Path (Join-Path $srcPath "*") -DestinationPath $zipPath -Force
  Write-Host " done"

  Write-Host "  Finding Lambda ($pattern)..." -NoNewline
  $fn = aws lambda list-functions `
    --region $Region `
    --query "Functions[?contains(FunctionName, '$pattern')].FunctionName | [0]" `
    --output text 2>$null

  if (-not $fn -or $fn -eq "None") {
    Write-Host " NOT FOUND" -ForegroundColor Red
    Write-Host "    Ensure TranslationService stack is deployed." -ForegroundColor Yellow
    continue
  }
  Write-Host " $fn"

  Write-Host "  Updating code..." -NoNewline
  try {
    aws lambda update-function-code `
      --function-name $fn `
      --zip-file "fileb://$zipPath" `
      --region $Region `
      --output text 2>&1 | Out-Null
    Write-Host " OK" -ForegroundColor Green

    # upload_proxy needs TABLE_NAME; copy from TranslateTrigger if missing
    if ($folder -eq "upload_proxy") {
      try {
        $triggerFn = aws lambda list-functions --region $Region `
          --query "Functions[?contains(FunctionName, 'TranslateTrigger')].FunctionName | [0]" --output text 2>$null
        if ($triggerFn -and $triggerFn -ne "None") {
          $tableName = aws lambda get-function-configuration --function-name $triggerFn --region $Region `
            --query "Environment.Variables.TABLE_NAME" --output text 2>$null
          if ($tableName -and $tableName -ne "None") {
            $curr = aws lambda get-function-configuration --function-name $fn --region $Region --output json 2>$null | ConvertFrom-Json
            $vars = @{}
            $curr.Environment.Variables.PSObject.Properties | ForEach-Object { $vars[$_.Name] = $_.Value }
            if (-not $vars["TABLE_NAME"]) {
              $vars["TABLE_NAME"] = $tableName
              $envFile = Join-Path $TempDir "upload_proxy_env.json"
              @{ Variables = $vars } | ConvertTo-Json -Depth 3 | Set-Content -Path $envFile -Encoding UTF8 -NoNewline
              Write-Host "  Adding TABLE_NAME to UploadProxy env..." -NoNewline
              $envJson = Get-Content $envFile -Raw
              aws lambda update-function-configuration --function-name $fn --region $Region --environment $envJson 2>&1 | Out-Null
              Write-Host " OK" -ForegroundColor Green
            }
          }
        }
      } catch { Write-Host " (skip)" -ForegroundColor Yellow }
    }
  } catch {
    Write-Host " FAILED" -ForegroundColor Red
    Write-Error $_
  }
}

Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue
Write-Host ""
Write-Host "Done." -ForegroundColor Cyan
