param(
    [string]$Destination = "data/openiti/bidayat-mujtahid"
)

$ErrorActionPreference = "Stop"

$repo = "OpenITI/0600AH"
$revision = "ea4bdc6517a49d07106f223aa0869aa7c21b9589"
$authorUri = "0595IbnRushdHafid"
$workUri = "0595IbnRushdHafid.BidayatMujtahid"
$versionUri = "0595IbnRushdHafid.BidayatMujtahid.JK000222-ara1"
$relativeDir = "data/$authorUri/$workUri"
$rawBase = "https://raw.githubusercontent.com/$repo/$revision/$relativeDir"
$blobBase = "https://github.com/$repo/blob/$revision/$relativeDir"

New-Item -ItemType Directory -Force -Path $Destination | Out-Null

$downloads = @(
    @{ Url = "$rawBase/$versionUri"; Out = "$Destination/$versionUri" },
    @{ Url = "$rawBase/$versionUri.yml"; Out = "$Destination/$versionUri.yml" },
    @{ Url = "$rawBase/$workUri.yml"; Out = "$Destination/$workUri.yml" },
    @{ Url = "https://raw.githubusercontent.com/$repo/$revision/data/$authorUri/$authorUri.yml"; Out = "$Destination/$authorUri.yml" }
)

foreach ($item in $downloads) {
    Write-Host "Downloading $($item.Url)"
    Invoke-WebRequest -Uri $item.Url -OutFile $item.Out
}

$manifest = [ordered]@{
    provider = "OpenITI"
    repository = $repo
    revision = $revision
    version_uri = $versionUri
    source_url = "$blobBase/$versionUri"
    downloaded_at_utc = (Get-Date).ToUniversalTime().ToString("o")
}

$manifest | ConvertTo-Json | Set-Content -Encoding UTF8 "$Destination/manifest.json"

Write-Host ""
Write-Host "Downloaded to $Destination"
Write-Host "Pinned revision: $revision"
Write-Host "Version URI: $versionUri"
Write-Host "Quality remains UNREVIEWED until editorial validation."
