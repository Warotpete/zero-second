# Deploying Zero Second to Azure

About 45 minutes the first time. Portal labels change often; if a button is named slightly differently, look for the closest match.

## 1. Azure account
1. Create an account at https://azure.microsoft.com/free (new accounts get free credit). Use the same Microsoft account as the hackathon if you like.
2. Install the Azure CLI on Windows:
   ```powershell
   winget install -e --id Microsoft.AzureCLI
   ```
   Open a new terminal, then:
   ```powershell
   az login
   az account show
   ```

## 2. Microsoft Foundry project and model
1. Go to https://ai.azure.com and sign in.
2. **Create project** (this also creates a Foundry resource). Pick a region where your chosen model is available (for example East US 2 or Sweden Central). Resource group: `zero-second-rg`.
3. In the project, open **Models + endpoints** (or **Model catalog**) and **Deploy** a chat model. A small, fast model is ideal: for example `gpt-4.1-mini` or `gpt-4o-mini`. Note the **deployment name**.
4. On the project **Overview** page copy the **project endpoint**. It looks like
   `https://<resource>.services.ai.azure.com/api/projects/<project>`.
5. Note the Foundry **resource ID** (resource page → JSON View / Properties). It looks like
   `/subscriptions/<sub>/resourceGroups/zero-second-rg/providers/Microsoft.CognitiveServices/accounts/<resource>`.

## 3. Test Foundry locally
1. Copy `backend/.env.example` to `backend/.env` and fill in:
   ```
   FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
   FOUNDRY_MODEL=<deployment name>
   ```
2. Your own account needs the **Foundry User** role on the Foundry resource (the project creator usually has it).
3. Start the API (`az login` must be done). The log should say `Foundry agents ready (model …)` and the status bar in the Media Desk shows **Foundry · <model>**.
4. Jump to 66' on the Live page and open **Agent Trace**: lanes show real model latency and the Editor's MCP tool calls.

If an agent call fails or times out, Zero Second falls back to the deterministic writer and logs it in the audit log, so the demo never breaks.

## 4. Deploy to Azure Container Apps
From the repository root in PowerShell:
```powershell
./infra/deploy.ps1 `
  -FoundryEndpoint "https://<resource>.services.ai.azure.com/api/projects/<project>" `
  -FoundryModel "<deployment name>" `
  -FoundryResourceId "/subscriptions/<sub>/resourceGroups/zero-second-rg/providers/Microsoft.CognitiveServices/accounts/<resource>"
```
The script:
- builds the Docker image in Azure Container Registry and creates the Container App (`az containerapp up`),
- pins it to one always-on replica (live rooms are in memory; no cold starts for judges),
- turns on a managed identity and grants it **Foundry User** on the Foundry resource (no keys),
- prints the public URL.

Check logs: `az containerapp logs show -n zero-second -g zero-second-rg --follow`

## 5. Keep it running until judging ends (10 Nov 2026)
The rules require a working, free demo link until the end of judging. One small replica plus light model usage should stay within free credit, but **set a budget alert** (Cost Management → Budgets) to be safe. Delete the resource group after 20 Nov if you don't need it: `az group delete -n zero-second-rg`.
