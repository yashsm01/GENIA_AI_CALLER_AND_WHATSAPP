# 🌐 Ngrok Setup Guide

To test the AI Auto Caller locally, you need to expose your local server (`localhost:8000`) to the internet so that Twilio can send webhooks and media streams to it. **Ngrok** is the easiest way to do this.

---

## 1. Install Ngrok

If you don't have ngrok installed:
- **Download**: Visit [ngrok.com/download](https://ngrok.com/download)
- **Windows (Chocolatey)**: `choco install ngrok`
- **Mac (Homebrew)**: `brew install ngrok/ngrok/ngrok`

---

## 2. Authenticate (First Time Only)

1. Sign up for a free account at [ngrok.com](https://ngrok.com).
2. Get your **Auth Token** from the [dashboard](https://dashboard.ngrok.com/get-started/your-authtoken).
3. Run the following in your terminal:
   ```bash
   ngrok config add-authtoken <YOUR_AUTH_TOKEN>
   ```

---

## 3. Start the Tunnel

Start the tunnel for your FastAPI server (which runs on port 8000 by default):

```bash
ngrok http 8000
```

You will see an interface in your terminal. Look for the **Forwarding** line:
`Forwarding                    https://a1b2-c3d4.ngrok-free.app -> http://localhost:8000`

---

## 4. Update Your `.env` File

Copy the HTTPS URL from ngrok (e.g., `https://a1b2-c3d4.ngrok-free.app`) and paste it into your `.env` file:

```env
PUBLIC_BASE_URL=https://a1b2-c3d4.ngrok-free.app
```

> [!IMPORTANT]
> Every time you restart ngrok on a free plan, the URL changes. You must update the `.env` file and restart your `main.py` server.

---

## 5. Configure Twilio

1. Go to your **Twilio Console** > **Phone Numbers** > **Manage** > **Active Numbers**.
2. Click on your phone number (`+12182170603`).
3. Scroll down to **Voice & Fax**.
4. Under **A CALL COMES IN**, set:
   - **Method**: `HTTP POST`
   - **URL**: `https://a1b2-c3d4.ngrok-free.app/call/inbound`
5. Click **Save**.

---

## 6. Test It

1. Ensure your server is running: `python main.py`
2. Dial your Twilio number from your phone.
3. You should see the logs in your terminal and hear the AI greeting!
