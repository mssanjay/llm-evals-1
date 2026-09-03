param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string]$WorkspaceName,

    [Parameter(Mandatory = $true)]
    [string]$ComputeName,

    [ValidateSet("dryrun", "mock", "openrouter", "aws", "azure-foundry", "azure-ai", "azure-openai")]
    [string]$Provider = "dryrun",

    [ValidateSet(1, 2)]
    [int]$Experiment = 2,

    [string]$Model = "qwen3-32b",
    [int]$Limit = 100,
    [int]$MaxTokens = 256,
    [double]$Temperature = 0.2,
    [string]$AzureAiEndpoint = $env:AZURE_AI_ENDPOINT,
    [string]$AzureAiApiKey = $env:AZURE_AI_API_KEY,
    [string]$AzureAiApiVersion = $env:AZURE_AI_API_VERSION,
    [string]$AzureOpenAiEndpoint = $env:AZURE_OPENAI_ENDPOINT,
    [string]$AzureOpenAiApiKey = $env:AZURE_OPENAI_API_KEY,
    [string]$AzureOpenAiApiVersion = $env:AZURE_OPENAI_API_VERSION,
    [string]$OpenRouterApiKey = $env:OPENROUTER_API_KEY,
    [string]$OpenRouterBaseUrl = $env:OPENROUTER_BASE_URL,
    [string]$OpenRouterSiteUrl = $env:OPENROUTER_SITE_URL,
    [string]$OpenRouterAppName = $env:OPENROUTER_APP_NAME,
    [string]$AwsRegion = $env:AWS_BEDROCK_REGION,
    [string]$AwsBearerTokenBedrock = $env:AWS_BEARER_TOKEN_BEDROCK,
    [string]$AwsBedrockMantleBaseUrl = $env:AWS_BEDROCK_MANTLE_BASE_URL,
    [switch]$PrepareDatasets,
    [switch]$NoSubmit
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$JobDir = Join-Path $RepoRoot "outputs\azureml_jobs"
$JobFile = Join-Path $JobDir "experiment_$Experiment.generated.yml"
New-Item -ItemType Directory -Force $JobDir | Out-Null

if (-not $AzureAiApiVersion) {
    $AzureAiApiVersion = "2024-05-01-preview"
}

if (-not $AzureOpenAiApiVersion) {
    $AzureOpenAiApiVersion = "2024-10-21"
}

if (-not $OpenRouterBaseUrl) {
    $OpenRouterBaseUrl = "https://openrouter.ai/api/v1/chat/completions"
}

if (-not $OpenRouterAppName) {
    $OpenRouterAppName = "llm-cue-evals"
}

if (-not $AwsRegion) {
    $AwsRegion = $env:AWS_REGION
}

if (-not $AwsRegion) {
    $AwsRegion = $env:AWS_DEFAULT_REGION
}

$runner = if ($Experiment -eq 1) { "scripts/experiment_1.py" } else { "scripts/run_experiment2.py" }
$displayName = if ($Experiment -eq 1) { "experiment-1-multiturn-story-comparison" } else { "experiment-2-live-history-comparison" }
$description = if ($Experiment -eq 1) {
    "Experiment 1: compare shortcut rate by wrong-answer cue count inside one story."
} else {
    "Experiment 2: compare probe shortcut rate by how many teaching turns held the planted rule."
}
$outputName = if ($Experiment -eq 1) { "azure_experiment_1" } else { "azure_experiment2" }

# Keep jobs focused on the already prepared 100-line files by default.
$prepareFlag = ""
if ($Experiment -eq 1) {
    $prepareFlag = if ($PrepareDatasets) { "" } else { "--skip-prepare --prepared-dir data" }
} else {
    $prepareFlag = "--prepared-dir data --story-pool data/story_pool.jsonl"
    if ($PrepareDatasets) {
        Write-Host "PrepareDatasets is ignored for Experiment 2. Regenerate data locally before submitting."
    }
}

$command = "python $runner --provider $Provider $prepareFlag --limit $Limit --max-tokens $MaxTokens --temperature $Temperature --output-dir outputs/$outputName"
if ($Provider -notin @("dryrun", "mock")) {
    $command = "$command --model $Model"
}

$lines = @(
    '$schema: https://azuremlschemas.azureedge.net/latest/commandJob.schema.json',
    "display_name: `"$displayName`"",
    'experiment_name: "cue-following-demo"',
    "description: `"$description`"",
    'code: ../..',
    'command: >-',
    "  $command",
    'environment:',
    '  image: mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04',
    '  conda_file: ../../azureml/conda.yml'
)

if ($Provider -eq "azure-ai") {
    if (-not $AzureAiEndpoint -or -not $AzureAiApiKey) {
        throw "Set AZURE_AI_ENDPOINT and AZURE_AI_API_KEY, or pass -AzureAiEndpoint and -AzureAiApiKey."
    }
    $lines += @(
        'environment_variables:',
        "  AZURE_AI_ENDPOINT: `"$AzureAiEndpoint`"",
        "  AZURE_AI_API_KEY: `"$AzureAiApiKey`"",
        "  AZURE_AI_API_VERSION: `"$AzureAiApiVersion`""
    )
}

if ($Provider -eq "azure-foundry") {
    if (-not $AzureAiEndpoint -or -not $AzureAiApiKey) {
        throw "Set AZURE_AI_ENDPOINT and AZURE_AI_API_KEY, or pass -AzureAiEndpoint and -AzureAiApiKey."
    }
    $lines += @(
        'environment_variables:',
        "  AZURE_AI_ENDPOINT: `"$AzureAiEndpoint`"",
        "  AZURE_AI_API_KEY: `"$AzureAiApiKey`""
    )
}

if ($Provider -eq "openrouter") {
    if (-not $OpenRouterApiKey) {
        throw "Set OPENROUTER_API_KEY, or pass -OpenRouterApiKey."
    }
    $lines += @(
        'environment_variables:',
        "  OPENROUTER_API_KEY: `"$OpenRouterApiKey`"",
        "  OPENROUTER_BASE_URL: `"$OpenRouterBaseUrl`"",
        "  OPENROUTER_APP_NAME: `"$OpenRouterAppName`""
    )
    if ($OpenRouterSiteUrl) {
        $lines += "  OPENROUTER_SITE_URL: `"$OpenRouterSiteUrl`""
    }
}

if ($Provider -eq "aws") {
    if (-not $AwsRegion) {
        throw "Set AWS_BEDROCK_REGION, AWS_REGION, or AWS_DEFAULT_REGION, or pass -AwsRegion."
    }
    if (-not $AwsBearerTokenBedrock) {
        throw "Set AWS_BEARER_TOKEN_BEDROCK before submitting an Azure ML job that calls Bedrock Mantle."
    }
    $lines += @(
        'environment_variables:',
        "  AWS_BEDROCK_REGION: `"$AwsRegion`"",
        "  AWS_BEARER_TOKEN_BEDROCK: `"$AwsBearerTokenBedrock`""
    )
    if ($AwsBedrockMantleBaseUrl) {
        $lines += "  AWS_BEDROCK_MANTLE_BASE_URL: `"$AwsBedrockMantleBaseUrl`""
    }
}

if ($Provider -eq "azure-openai") {
    if (-not $AzureOpenAiEndpoint -or -not $AzureOpenAiApiKey) {
        throw "Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY, or pass -AzureOpenAiEndpoint and -AzureOpenAiApiKey."
    }
    $lines += @(
        'environment_variables:',
        "  AZURE_OPENAI_ENDPOINT: `"$AzureOpenAiEndpoint`"",
        "  AZURE_OPENAI_API_KEY: `"$AzureOpenAiApiKey`"",
        "  AZURE_OPENAI_API_VERSION: `"$AzureOpenAiApiVersion`""
    )
}

$lines += "compute: azureml:$ComputeName"
Set-Content -Path $JobFile -Value $lines -Encoding UTF8

Write-Host "Generated Azure ML job file:"
Write-Host $JobFile

if ($NoSubmit) {
    Write-Host "NoSubmit was set, so the job was not submitted."
    exit 0
}

# Ensure the Azure ML extension is present before submitting.
az extension add --name ml --upgrade | Out-Null

az ml job create `
    --file $JobFile `
    --resource-group $ResourceGroup `
    --workspace-name $WorkspaceName
