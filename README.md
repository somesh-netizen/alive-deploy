# ALIVE Deploy

One-click deployment of ALIVE agents to Cloudflare Workers + Containers with GitHub Actions CI/CD.

## Quick Start

### 1. Export Agent from ALIVE
- Go to http://localhost:5180
- Click **Export**
- Select **"Cloudflare Workers + Containers (Live URL)"**
- Download the bundle

### 2. Add to alive-deploy
```bash
unzip exported_agent.zip -d agents/
cd agents/your_agent_name
```

### 3. Push to GitHub
```bash
git add agents/
git commit -m "Add agent: your_agent_name"
git push
```

### 4. GitHub Actions automatically:
✅ Builds Docker image using docker-buildx (no local Docker needed!)
✅ Pushes to GitHub Container Registry (ghcr.io)
✅ Deploys to Cloudflare Workers + Containers
✅ Generates public Cloudflare URL

### 5. Access Your Agent
Your agent is live at the Cloudflare URL! Anyone can access it.

## Directory Structure

```
alive-deploy/
├── agents/
│   ├── customer_support_ops/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── wrangler.jsonc
│   │   └── ...
│   └── another_agent/
│       ├── Dockerfile
│       └── ...
└── .github/workflows/
    └── deploy-agents.yml
```

## Requirements

- Cloudflare account with API token
- GitHub repository secrets configured:
  - `CLOUDFLARE_API_TOKEN`
  - `CLOUDFLARE_ACCOUNT_ID`

## How It Works

1. **Export from ALIVE** → Generates Docker bundle
2. **Push to GitHub** → Triggers GitHub Actions
3. **GitHub Actions builds image** → docker-buildx (no local Docker!)
4. **Push to ghcr.io** → GitHub Container Registry
5. **Deploy to Cloudflare** → wrangler deploy
6. **Public URL** → Live agent accessible to anyone

No Docker Desktop needed. No manual builds. One-click deployment! 🚀
