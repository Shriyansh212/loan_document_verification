# Deployment Guide — Document Verification Pipeline

This guide outlines multiple zero-cost options to deploy the **Document Verification Pipeline** with a public **Live Demo** URL suitable for your resume and portfolio.

---

## 🌟 Option 1: Render (Recommended — 1-Click Docker Deployment)

[Render](https://render.com) provides a free cloud tier that natively executes Docker containers.

### Steps:
1. **Push your repository to GitHub**:
   Ensure this project is pushed to your GitHub repository (e.g., `https://github.com/Shriyansh212/document-verification-pipeline`).

2. **Deploy via Render Blueprint**:
   - Log in to your Render account at [dashboard.render.com](https://dashboard.render.com/).
   - Click **New +** > **Blueprint**.
   - Connect your GitHub repository `document-verification-pipeline`.
   - Render will detect `render.yaml` automatically.
   - Click **Apply**.

3. **Set your Groq API Key**:
   - In the Render dashboard for your service, go to **Environment**.
   - Add `GROQ_API_KEY` with your free key from [console.groq.com](https://console.groq.com).

4. **Your Live Demo URL**:
   Render will deploy your app at:
   ```
   https://document-verification-pipeline.onrender.com
   ```
   Add this link directly to your resume under **Live Demo**!

---

## 🤗 Option 2: Hugging Face Spaces (Free Docker Hosting with GPU/CPU)

Hugging Face Spaces provides perpetual free Docker hosting with instant public HTTPS URLs.

### Steps:
1. Go to [huggingface.co/new-space](https://huggingface.co/new-space).
2. Enter Space Name: `document-verification-pipeline`.
3. Select **Docker** as the Space SDK (Blank template).
4. Set visibility to **Public**.
5. Push your code to the Hugging Face git remote:
   ```bash
   git remote add space https://huggingface.co/spaces/Shriyansh212/document-verification-pipeline
   git push space main
   ```
6. Under **Settings > Variables and secrets**, add `GROQ_API_KEY`.
7. Your app is live at:
   ```
   https://huggingface.co/spaces/Shriyansh212/document-verification-pipeline
   ```

---

## 🚂 Option 3: Railway

1. Go to [railway.app](https://railway.app) and click **New Project** > **Deploy from GitHub repo**.
2. Select `document-verification-pipeline`.
3. Railway automatically detects the `Dockerfile` and deploys it.
4. Under **Variables**, add `GROQ_API_KEY`.
5. Under **Settings > Networking**, click **Generate Domain** to get your public URL.

---

## 📝 Testing Your Live Deployment

Once deployed, you can verify your service:
- Open the root URL (`/`) in your browser to test the interactive UI and sample presets.
- Check health: `GET /health` -> `{"status": "healthy"}`
- Test OpenAPI documentation: `GET /docs`
