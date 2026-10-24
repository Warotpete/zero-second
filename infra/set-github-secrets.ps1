<#
  Lets GitHub Actions push the Zero Second image to your Azure Container Registry.
  Turns on the registry's admin login and saves it as three secrets in the GitHub repo
  (ACR_LOGIN_SERVER, ACR_USERNAME, ACR_PASSWORD). Values are piped, never printed.

  Run from the repository root:  ./infra/set-github-secrets.ps1
#>
param(
  [string]$Registry = "ca6d61606078acr",
  [string]$Repo = "Warotpete/zero-second"
)
$env:Path = 'C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin;' + $env:Path
az acr update -n $Registry --admin-enabled true --only-show-errors | Out-Null
$server = az acr show -n $Registry --query loginServer -o tsv
$user = az acr credential show -n $Registry --query username -o tsv
$pass = az acr credential show -n $Registry --query "passwords[0].value" -o tsv
$server | gh secret set ACR_LOGIN_SERVER -R $Repo
$user | gh secret set ACR_USERNAME -R $Repo
$pass | gh secret set ACR_PASSWORD -R $Repo
gh secret list -R $Repo
Write-Host "Done. Re-run the image build with: gh workflow run image.yml -R $Repo"
