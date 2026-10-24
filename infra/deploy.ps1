<#
  Deploy Zero Second to Azure Container Apps (one container: web app + API + MCP server + agents).

  Prerequisites: Azure CLI (winget install Microsoft.AzureCLI), `az login`,
  and a Microsoft Foundry project with a model deployment (see docs/DEPLOY.md).

  Usage:
    ./infra/deploy.ps1 -FoundryEndpoint "https://<resource>.services.ai.azure.com/api/projects/<project>" `
                       -FoundryModel "gpt-4.1-mini" -FoundryResourceId "/subscriptions/.../accounts/<resource>"
#>
param(
  [string]$ResourceGroup = "zero-second-rg",
  [string]$Location = "eastus2",
  [string]$AppName = "zero-second",
  [string]$FoundryEndpoint = "",
  [string]$FoundryModel = "",
  [string]$FoundryResourceId = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

az extension add --name containerapp --upgrade --only-show-errors | Out-Null
az group create -n $ResourceGroup -l $Location --only-show-errors | Out-Null

$envVars = @("ZS_LLM=auto")
if ($FoundryEndpoint) { $envVars += "FOUNDRY_PROJECT_ENDPOINT=$FoundryEndpoint" }
if ($FoundryModel) { $envVars += "FOUNDRY_MODEL=$FoundryModel" }

# Builds the Dockerfile in Azure Container Registry and creates the Container App + environment.
az containerapp up `
  --name $AppName `
  --resource-group $ResourceGroup `
  --location $Location `
  --source $root `
  --ingress external `
  --target-port 8000 `
  --env-vars $envVars

# One replica: live match rooms are kept in memory. Always on, so judges never hit a cold start.
az containerapp update -n $AppName -g $ResourceGroup --min-replicas 1 --max-replicas 1 --cpu 1 --memory 2Gi --only-show-errors | Out-Null

# Managed identity -> Foundry (no keys in the app).
$principal = az containerapp identity assign -n $AppName -g $ResourceGroup --system-assigned --query principalId -o tsv
if ($FoundryResourceId) {
  az role assignment create --assignee-object-id $principal --assignee-principal-type ServicePrincipal `
    --role "Azure AI User" --scope $FoundryResourceId --only-show-errors | Out-Null
  Write-Host "Granted 'Azure AI User' on the Foundry resource to the app's managed identity."
}

$fqdn = az containerapp show -n $AppName -g $ResourceGroup --query properties.configuration.ingress.fqdn -o tsv
Write-Host ""
Write-Host "Zero Second is live: https://$fqdn"
Write-Host "Media Desk: https://$fqdn/desk    Fan View: https://$fqdn/fan    MCP: https://$fqdn/mcp/"
