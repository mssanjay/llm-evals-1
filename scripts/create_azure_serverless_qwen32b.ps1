param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string]$WorkspaceName,

    [string]$EndpointName = "qwen3-32b",
    [string]$ModelId = "azureml://registries/azureml-alibaba/models/qwen3-32b/versions/1",
    [switch]$NoSubmit
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$OutputDir = Join-Path $RepoRoot "outputs\azureml_serverless"
$EndpointFile = Join-Path $OutputDir "$EndpointName.endpoint.yml"
New-Item -ItemType Directory -Force $OutputDir | Out-Null

# The endpoint name is also the model/deployment name used by the inference API.
$lines = @(
    "name: `"$EndpointName`"",
    "model_id: `"$ModelId`""
)
Set-Content -Path $EndpointFile -Value $lines -Encoding UTF8

Write-Host "Generated serverless endpoint file:"
Write-Host $EndpointFile

if ($NoSubmit) {
    Write-Host "NoSubmit was set, so the endpoint was not created."
    exit 0
}

az extension add --name ml --upgrade | Out-Null

az ml serverless-endpoint create `
    --file $EndpointFile `
    --resource-group $ResourceGroup `
    --workspace-name $WorkspaceName

Write-Host ""
Write-Host "Endpoint created or updated. Get its key with:"
Write-Host "az ml serverless-endpoint get-credentials --name $EndpointName --resource-group $ResourceGroup --workspace-name $WorkspaceName"
Write-Host ""
Write-Host "Use the endpoint Target URI as AZURE_AI_ENDPOINT and run with:"
Write-Host "--provider azure-foundry --model $EndpointName"
