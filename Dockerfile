FROM python:3.12-slim

# 1. Install dependencies for Chrome, Xvfb, and GPG management
# Note: 'libgbm1' is critical for newer Chrome
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    xvfb \
    libxi6 \
    libnss3 \
    libgbm1 \
    libasound2 \
    fonts-liberation \
    libappindicator3-1 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Google Chrome Stable (Modern Keyring Method)
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable

# 3. Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy code and scripts
WORKDIR /app
COPY scraper.py .
COPY entrypoint.sh .

# 5. Make entrypoint executable
RUN chmod +x entrypoint.sh

# 6. Run the entrypoint
CMD ["./entrypoint.sh"]