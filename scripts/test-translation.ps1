# Test script for PDF Poly Lingo translation service
# Usage: .\test-translation.ps1 -ApiEndpoint "https://xxx.execute-api.us-west-2.amazonaws.com/prod/"

param(
    [Parameter(Mandatory=$true)]
    [string]$ApiEndpoint,
    [string]$TestFile = "test.txt",
    [string]$TargetLanguage = "es"
)

$apiUrl = $ApiEndpoint.TrimEnd("/")

# Ensure test file exists
if (-not (Test-Path $TestFile)) {
    "Hello world. This is a test document for translation." | Out-File -FilePath $TestFile -Encoding utf8
    Write-Host "Created $TestFile"
}

$filename = Split-Path $TestFile -Leaf

# Step 1: Get presigned URL
Write-Host "`n1. Requesting presigned URL..."
$body = @{
    filename = $filename
    target_language = $TargetLanguage
    source_language = "auto"
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri "$apiUrl/presigned-url" -Method POST -Body $body -ContentType "application/json"
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
}

Write-Host "   Got upload_url and key: $($response.key)"

# Step 2: Upload file
Write-Host "`n2. Uploading $TestFile..."
$contentType = switch -Wildcard ($filename) {
    "*.html" { "text/html" }
    "*.htm"  { "text/html" }
    default  { "text/plain" }
}

try {
    Invoke-WebRequest -Uri $response.upload_url -Method PUT -InFile $TestFile -ContentType $contentType -UseBasicParsing | Out-Null
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
}

Write-Host "   Upload complete."
Write-Host "`n3. Translation job started. Check S3 output bucket in 1-3 minutes."
Write-Host "   Or subscribe to SNS topic for completion notification."
