#!/bin/bash

# Set Git username and email
git config --global user.name "Akash Gurava"
git config --global user.email "akashgurava@outlook.com"

echo "1. Acquiring SUDO."
sudo -v
while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null &
echo "1. Acquiring SUDO. Complete."

echo "2. Install Xcode CLI tools."
if ! xcode-select -p &> /dev/null; then
    echo "Installing Xcode CLI tools..."
    xcode-select --install
    # Wait for the installation to complete
    until xcode-select -p &> /dev/null; do
        sleep 5
    done
fi
echo "2. Install Xcode CLI tools. Comeplete."

echo "3. Install brew."
if ! command -v brew &> /dev/null; then
    echo "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add Homebrew to PATH
    echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> $HOME/.zprofile
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi
echo "3. Install brew. Complete."

echo "4. Install packages from Brewfile."
if [ -f "Brewfile" ]; then
    echo "Installing packages from Brewfile..."
    brew bundle --file="$Brewfile"
fi
echo "4. Install packages from Brewfile. Complete."
