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

### Paid subscriptions: one script
`./infra/deploy.ps1 -FoundryEndpoint … -FoundryModel … -FoundryResourceId …` builds the image in Azure Container Registry and creates the app (`az containerapp up`).

### Free Trial subscriptions (what the live demo uses)
Free Trial blocks ACR cloud builds (`TasksOperationsNotAllowed`), so GitHub Actions builds the image instead:

1. Create the registry and environment once (the first `deploy.ps1` run does this even when the build step fails).
2. `powershell -ExecutionPolicy Bypass -File .\infra\set-github-secrets.ps1` stores the registry login as GitHub secrets.
3. Every push to `main` that touches the app runs `.github/workflows/image.yml`, which pushes `zero-second:<sha>` and `:latest` to the registry.
4. First time only, create the app (it pulls with its own managed identity, no passwords):
   ```powershell
   az containerapp create -n zero-second -g zero-second-rg --environment zero-second-env `
     --image <registry>.azurecr.io/zero-second:latest --registry-server <registry>.azurecr.io --registry-identity system `
     --system-assigned --ingress external --target-port 8000 --min-replicas 1 --max-replicas 1 --cpu 1 --memory 2Gi `
     --env-vars ZS_LLM=auto FOUNDRY_PROJECT_ENDPOINT=<endpoint> FOUNDRY_MODEL=gpt-5-mini ZS_REASONING_EFFORT=low
   ```
5. Grant the app's identity **Foundry User** and **Cognitive Services OpenAI User** on the Foundry resource. Allow up to 10 minutes for the roles to apply (until then you'll see 403s and the deterministic fallback).
6. To release a new build: `az containerapp update -n zero-second -g zero-second-rg --image <registry>.azurecr.io/zero-second:<sha>`

Check logs: `az containerapp logs show -n zero-second -g zero-second-rg --follow`

## 5. Keep it running until judging ends (10 Nov 2026)
The rules require a working, free demo link until the end of judging. One small replica plus light model usage should stay within free credit, but **set a budget alert** (Cost Management → Budgets) to be safe. Delete the resource group after 20 Nov if you don't need it: `az group delete -n zero-second-rg`.
