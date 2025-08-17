# Gmail Groq Worker

An AI-powered Gmail automation tool that uses Groq's fast inference API to intelligently classify and organize your emails. This application automatically processes incoming emails, identifies spam, marks important messages, and organizes your inbox.

## Features

- **Intelligent Spam Detection**: Uses AI to identify spam, including form submissions with random data
- **Important Email Recognition**: Automatically identifies and stars important emails
- **Smart Organization**: Archives newsletters and non-essential emails
- **Gmail Labels**: Creates custom labels for tracking processed and important emails
- **Rate Limiting**: Gentle API usage to respect rate limits

## Cloud Deployment

This application is designed to run continuously in the cloud to automatically process your emails.

### Prerequisites

1. **Groq API Key**: Get one from [Groq Console](https://console.groq.com/keys)
2. **Gmail API Credentials**: 
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Enable the Gmail API
   - Create OAuth 2.0 credentials
   - Download the `client_secret.json` file

### Deploy to Railway (Recommended)

1. Fork this repository on GitHub
2. Go to [Railway.app](https://railway.app) and sign up
3. Create a new project from your GitHub repository
4. Set environment variables:
   - `GROQ_API_KEY`: Your Groq API key
5. Upload your `client_secret.json` file to the Railway file system
6. Deploy!

### Deploy to Render

**Option A: Background Worker (Recommended)**
1. Go to [Render.com](https://render.com) and sign up
2. Create a new **Background Worker** from your GitHub repository
3. Use Docker as the runtime
4. Set environment variables:
   - `GROQ_API_KEY`: Your Groq API key
5. Upload your `client_secret.json` and `token.json` files
6. Deploy!

**Option B: Web Service (with health check server)**
1. Go to [Render.com](https://render.com) and sign up
2. Create a new **Web Service** from your GitHub repository
3. Use Docker as the runtime
4. Set environment variables:
   - `GROQ_API_KEY`: Your Groq API key
5. Upload your `client_secret.json` and `token.json` files
6. Deploy! (The service will automatically bind to port 10000 for health checks)

### Environment Variables

- `GROQ_API_KEY` (required): Your Groq API key for AI inference

### Initial Setup (IMPORTANT - Do this first!)

Before deploying to the cloud, you MUST complete OAuth authentication locally:

1. **Run locally first**: `python setup_auth.py`
2. **Complete OAuth flow** in your browser when prompted
3. **Upload the generated `token.json` file** to your cloud service
4. **Set environment variables** and deploy

⚠️ **Cloud services can't run interactive OAuth flows**, so you must generate the `token.json` file locally first.

## Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/TeddyJubu/gmail-groq-worker.git
   cd gmail-groq-worker
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

4. Add your Gmail credentials:
   - Place `client_secret.json` in the project root
   - Run the script once to generate `token.json`

5. Run the application:
   ```bash
   python gmail_groq_worker.py
   ```

## How It Works

1. **Email Retrieval**: Fetches unprocessed emails from the last 7 days
2. **Content Extraction**: Extracts text content from email bodies
3. **AI Classification**: Uses Groq's AI to classify each email
4. **Action Application**: Applies labels, archiving, or spam marking based on classification
5. **Statistics**: Provides a summary of actions taken

## Security

- OAuth tokens are stored locally and not exposed in logs
- Sensitive files are excluded from version control via `.gitignore`
- The application uses minimal required Gmail API permissions

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

MIT License - feel free to use and modify as needed.
