#!/bin/bash

# KYC Document Processing Pipeline - Quick Setup Script

echo "🚀 Setting up KYC Document Processing Pipeline..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8+ first."
    exit 1
fi

echo "✅ Python found: $(python3 --version)"

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed. Please install pip first."
    exit 1
fi

echo "✅ pip found"

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip3 install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ Failed to install Python dependencies"
    exit 1
fi

echo "✅ Python dependencies installed"

# Check if Tesseract is installed
if ! command -v tesseract &> /dev/null; then
    echo "⚠️  Tesseract OCR not found. Installing..."
    
    # Try to install Tesseract based on OS
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        sudo apt-get update
        sudo apt-get install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install tesseract tesseract-lang
        else
            echo "❌ Homebrew not found. Please install Tesseract manually:"
            echo "   brew install tesseract tesseract-lang"
            exit 1
        fi
    else
        echo "❌ Unsupported OS. Please install Tesseract OCR manually."
        exit 1
    fi
else
    echo "✅ Tesseract OCR found: $(tesseract --version | head -n1)"
fi

# Setup environment file
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    
    echo ""
    echo "⚠️  IMPORTANT: Please edit .env file and add your GROQ_API_KEY"
    echo "   1. Get free API key from: https://console.groq.com/"
    echo "   2. Edit .env file and replace 'your_groq_api_key_here' with your actual key"
    echo ""
else
    echo "✅ .env file already exists"
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Next steps:"
echo "1. Make sure you have added your GROQ_API_KEY to .env file"
echo "2. Run the server: python3 main.py"
echo "3. Open browser: http://localhost:8000"
echo ""
echo "For more information, see README.md"