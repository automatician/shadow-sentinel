#!/usr/bin/env bash
set -e

CLR_RESET="\033[0m"
CLR_ICE="\033[38;5;195m"
CLR_CYAN="\033[38;5;33m"
CLR_GREEN="\033[38;5;82m"
CLR_YELLOW="\033[38;5;220m"

echo -e "${CLR_ICE}───────────────────────────────────────────────────────────────────────────────${CLR_RESET}"
echo -e " ${CLR_CYAN}Shadow Sentinel${CLR_RESET} ${CLR_ICE}– Universal Linux Installer (pipx preferred)${CLR_RESET}"
echo -e "${CLR_ICE}───────────────────────────────────────────────────────────────────────────────${CLR_RESET}"

if [ "$EUID" -ne 0 ]; then
    echo -e "${CLR_YELLOW}[WARN] Please run as root (e.g. curl -sSL ... | sudo bash)${CLR_RESET}"
    exit 1
fi

# 1. Sicherstellen, dass python3 und pipx verfügbar sind
if ! command -v pipx &> /dev/null; then
    echo -e " ${CLR_ICE}[SETUP] Installing pipx via system package manager...${CLR_RESET}"
    if command -v apt-get &> /dev/null; then
        apt-get update -qq && apt-get install -y -qq pipx python3-pip
    elif command -v dnf &> /dev/null; then
        dnf install -y -q pipx python3-pip
    elif command -v pacman &> /dev/null; then
        pacman -Sy --noconfirm python-pipx
    elif command -v apk &> /dev/null; then
        apk add --no-cache pipx py3-pip
    fi
fi

# 2. Installation über pipx (bevorzugt) oder Fallback
echo -e " ${CLR_ICE}[1/3] Installing shadow-sentinel...${CLR_RESET}"
INSTALLED=false

if command -v pipx &> /dev/null; then
    if pipx install shadow-sentinel --force > /dev/null 2>&1; then
        INSTALLED=true
    fi
fi

if [ "$INSTALLED" = false ]; then
    if python3 -m pip install --break-system-packages --upgrade shadow-sentinel > /dev/null 2>&1; then
        INSTALLED=true
    fi
fi

# 3. Systemd-Dienst aktivieren & neu starten
echo -e " ${CLR_ICE}[2/3] Configuring systemd background daemon...${CLR_RESET}"
if command -v sentinel &> /dev/null; then
    sentinel service install > /dev/null 2>&1 || true
    sentinel restart > /dev/null 2>&1 || true
elif [ -f /usr/local/bin/sentinel ]; then
    /usr/local/bin/sentinel service install > /dev/null 2>&1 || true
    /usr/local/bin/sentinel restart > /dev/null 2>&1 || true
fi

echo -e " ${CLR_ICE}[3/3] Verifying installation...${CLR_RESET}"
echo -e "${CLR_ICE}───────────────────────────────────────────────────────────────────────────────${CLR_RESET}"
echo -e " ${CLR_GREEN}✓ SUCCESS! Shadow Sentinel is installed via pipx and active.${CLR_RESET}"
echo -e "${CLR_ICE}───────────────────────────────────────────────────────────────────────────────${CLR_RESET}"
echo -e " Quick Start:"
echo -e "   1. Navigate to your project:  ${CLR_CYAN}cd /path/to/project${CLR_RESET}"
echo -e "   2. Arm the directory:         ${CLR_CYAN}sentinel init 5 1 4${CLR_RESET}"
echo -e "   3. Launch Explorer anytime:   ${CLR_CYAN}sentinel${CLR_RESET}"
echo -e "${CLR_ICE}───────────────────────────────────────────────────────────────────────────────${CLR_RESET}"
