#!/usr/bin/env bash
set -euo pipefail

# aolserver installer — run with: curl -fsSL https://raw.githubusercontent.com/kachowtowmater/aolserver/main/install.sh | bash
# or: bash install.sh

REPO="https://github.com/kachowtowmater/aolserver.git"
INSTALL_DIR="${AOL_DIR:-$HOME/aolserver}"
PORT="${AOL_PORT:-5190}"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
red() { printf "\033[31m%s\033[0m\n" "$*"; }
ask() { read -rp "$(bold "$1") " "$2" </dev/tty; }

banner() {
    echo
    bold "╔══════════════════════════════════════════════════════════╗"
    bold "║              aolserver — AOL 3.0/4.0 host               ║"
    bold "║        Original client, rebuilt server, 2026 content     ║"
    bold "╚══════════════════════════════════════════════════════════╝"
    echo
}

# ---------- detect OS ----------

detect_os() {
    case "$(uname -s)" in
        Linux*)  OS=linux ;;
        Darwin*) OS=macos ;;
        MINGW*|MSYS*|CYGWIN*) OS=windows ;;
        *)       OS=unknown ;;
    esac
    ARCH="$(uname -m)"
}

# ---------- check / install deps ----------

check_python() {
    for py in python3 python; do
        if command -v "$py" >/dev/null 2>&1; then
            ver=$("$py" -c 'import sys; print(sys.version_info >= (3, 10))' 2>/dev/null || echo False)
            if [ "$ver" = "True" ]; then
                PYTHON="$py"
                return 0
            fi
        fi
    done
    return 1
}

check_git() { command -v git >/dev/null 2>&1; }
check_chrome() { command -v chromium >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1 || command -v google-chrome >/dev/null 2>&1; }

install_deps() {
    bold "Checking dependencies..."
    local missing=()

    if ! check_python; then missing+=(python3); fi
    if ! check_git; then missing+=(git); fi

    if [ ${#missing[@]} -eq 0 ]; then
        green "  Python 3.10+: $($PYTHON --version)"
        green "  git: $(git --version)"
    else
        yellow "  Missing: ${missing[*]}"
        echo
        if [ "$OS" = "linux" ]; then
            if command -v apt-get >/dev/null 2>&1; then
                bold "Installing with apt..."
                sudo apt-get update -qq && sudo apt-get install -y -qq "${missing[@]}"
            elif command -v dnf >/dev/null 2>&1; then
                bold "Installing with dnf..."
                sudo dnf install -y -q "${missing[@]}"
            elif command -v pacman >/dev/null 2>&1; then
                bold "Installing with pacman..."
                sudo pacman -S --noconfirm --needed "${missing[@]}"
            else
                red "Please install ${missing[*]} manually and re-run this script."
                exit 1
            fi
        elif [ "$OS" = "macos" ]; then
            if command -v brew >/dev/null 2>&1; then
                bold "Installing with Homebrew..."
                brew install "${missing[@]}"
            else
                red "Please install Homebrew (https://brew.sh) and re-run, or install ${missing[*]} manually."
                exit 1
            fi
        else
            red "Please install ${missing[*]} and re-run this script."
            exit 1
        fi

        check_python || { red "Python 3.10+ is required."; exit 1; }
        check_git || { red "git is required."; exit 1; }
        green "  Dependencies installed."
    fi

    if check_chrome; then
        green "  Chrome/Chromium: found (World Wide Web will show real pages)"
    else
        yellow "  Chrome/Chromium: not found (Web browsing inside AOL will be text-only)"
        echo "  Install chromium for full web page rendering inside AOL."
    fi
    echo
}

# ---------- clone ----------

clone_repo() {
    if [ -d "$INSTALL_DIR/.git" ]; then
        bold "Updating existing installation in $INSTALL_DIR..."
        git -C "$INSTALL_DIR" pull --ff-only 2>/dev/null || git -C "$INSTALL_DIR" pull --rebase
    else
        bold "Downloading aolserver to $INSTALL_DIR..."
        git clone "$REPO" "$INSTALL_DIR"
    fi
    green "  Done."
    echo
}

# ---------- domain setup ----------

setup_domain() {
    bold "═══ Server configuration ═══"
    echo
    echo "Your server needs a hostname that AOL clients will connect to."
    echo "This can be a domain name (aol.example.com), a LAN hostname, or localhost."
    echo
    ask "Server hostname [localhost]:" HOSTNAME
    HOSTNAME="${HOSTNAME:-localhost}"
    echo

    bold "═══ Internet mail ═══"
    echo
    echo "Mail between members always works.  To let members send and receive"
    echo "real Internet email (screenname@yourdomain.com), set it up now."
    echo
    echo "  1) Skip for now (member-to-member mail only)"
    echo "  2) Use a Gmail/Fastmail/iCloud account (easiest)"
    echo "  3) Host your own domain (screenname@yourdomain.com)"
    echo
    ask "Choice [1]:" MAIL_CHOICE
    MAIL_CHOICE="${MAIL_CHOICE:-1}"

    case "$MAIL_CHOICE" in
        2)
            echo
            bold "Running mail setup wizard..."
            $PYTHON "$INSTALL_DIR/server/mailsetup.py"
            ;;
        3)
            echo
            ask "Your domain (e.g. my90s.net):" DOMAIN
            if [ -z "$DOMAIN" ]; then
                yellow "No domain entered, skipping mail setup."
            else
                echo
                bold "Setting up domain mail for $DOMAIN..."
                echo "You'll need to create DNS records after this step."
                echo
                local listen_port=2525
                ask "SMTP listen port [2525] (forward router port 25 here):" listen_port_in
                listen_port="${listen_port_in:-2525}"
                echo
                echo "For sending mail OUT, you need an SMTP relay (recommended) or direct delivery."
                echo "  1) SMTP relay (e.g. Gmail, Fastmail, SMTP2GO, Mailgun, Amazon SES)"
                echo "  2) Direct delivery (needs static IP, reverse DNS, outbound port 25)"
                echo
                ask "Outbound method [1]:" OUT_METHOD
                OUT_METHOD="${OUT_METHOD:-1}"

                if [ "$OUT_METHOD" = "1" ]; then
                    ask "SMTP relay host (e.g. smtp.gmail.com):" SMTP_HOST
                    ask "SMTP relay port [587]:" SMTP_PORT
                    SMTP_PORT="${SMTP_PORT:-587}"
                    ask "SMTP username:" SMTP_USER
                    echo -n "$(bold "SMTP password:") "
                    read -rs SMTP_PASS </dev/tty
                    echo
                    echo "$SMTP_PASS" | $PYTHON "$INSTALL_DIR/server/mailsetup.py" \
                        --mode domain --domain "$DOMAIN" --listen-port "$listen_port" \
                        --outbound relay --smtp-host "$SMTP_HOST" --smtp-port "$SMTP_PORT" \
                        --smtp-user "$SMTP_USER" --password-stdin
                else
                    $PYTHON "$INSTALL_DIR/server/mailsetup.py" \
                        --mode domain --domain "$DOMAIN" --listen-port "$listen_port" \
                        --outbound direct
                fi

                echo
                bold "DNS records to create:"
                $PYTHON "$INSTALL_DIR/server/mailsetup.py" --dns
            fi
            ;;
        *)
            echo "  Skipped.  Run '$INSTALL_DIR/run/mail-setup' any time to set it up."
            ;;
    esac
    echo
}

# ---------- services ----------

install_services() {
    bold "═══ Start on boot ═══"
    echo

    if [ "$OS" = "linux" ] && command -v systemctl >/dev/null 2>&1; then
        echo "Install systemd user service so aolserver starts automatically?"
        ask "[Y/n]:" INSTALL_SVC
        INSTALL_SVC="${INSTALL_SVC:-y}"
        if [[ "$INSTALL_SVC" =~ ^[Yy] ]]; then
            mkdir -p ~/.config/systemd/user
            # Write service file with correct paths
            cat > ~/.config/systemd/user/aol-server.service <<SVCEOF
[Unit]
Description=AOL revival host (P3 on :$PORT) for the original AOL 3.0/4.0 clients

[Service]
WorkingDirectory=$INSTALL_DIR/server
Environment=AOL_PORT=$PORT
ExecStart=$PYTHON -u server.py
Restart=on-failure
RestartSec=3
StandardOutput=append:$INSTALL_DIR/run/server.log
StandardError=append:$INSTALL_DIR/run/server.log

[Install]
WantedBy=default.target
SVCEOF
            systemctl --user daemon-reload
            systemctl --user enable --now aol-server
            green "  Service installed and started."
            echo "  Logs: $INSTALL_DIR/run/server.log"
            echo "  Stop:    systemctl --user stop aol-server"
            echo "  Restart: systemctl --user restart aol-server"
        fi
    elif [ "$OS" = "macos" ]; then
        echo "Install launchd agent so aolserver starts automatically?"
        ask "[Y/n]:" INSTALL_SVC
        INSTALL_SVC="${INSTALL_SVC:-y}"
        if [[ "$INSTALL_SVC" =~ ^[Yy] ]]; then
            PLIST=~/Library/LaunchAgents/com.aolserver.host.plist
            sed "s|REPO|$INSTALL_DIR|g" "$INSTALL_DIR/run/macos/com.aolserver.host.plist" > "$PLIST"
            launchctl load "$PLIST" 2>/dev/null || true
            green "  LaunchAgent installed."
        fi
    else
        echo "Start the server manually with: cd $INSTALL_DIR && $PYTHON start.py"
    fi
    echo
}

# ---------- firewall ----------

check_firewall() {
    bold "═══ Firewall ═══"
    echo
    echo "AOL clients connect to TCP port $PORT."
    if [ "$OS" = "linux" ]; then
        if command -v ufw >/dev/null 2>&1; then
            echo "Open it with: sudo ufw allow $PORT/tcp"
        elif command -v firewall-cmd >/dev/null 2>&1; then
            echo "Open it with: sudo firewall-cmd --add-port=$PORT/tcp --permanent && sudo firewall-cmd --reload"
        else
            echo "Make sure port $PORT is open in your firewall."
        fi
    elif [ "$OS" = "macos" ]; then
        echo "macOS allows incoming connections by default for user apps."
    fi
    echo "If clients connect from outside your LAN, also forward port $PORT on your router."
    echo
}

# ---------- client ----------

setup_client() {
    bold "═══ AOL 4.0 client ═══"
    echo
    echo "The server is ready. Now you need the original AOL 4.0 client to connect to it."
    echo
    echo "Download the client CD from archive.org:"
    echo "  cd $INSTALL_DIR && $PYTHON client40/aol40_client.py fetch"
    echo
    echo "Then install and configure it:"
    if [ "$OS" = "linux" ]; then
        echo "  # Linux (Wine):"
        echo "  export WINEPREFIX=~/.wine-aol4"
        echo "  wine $INSTALL_DIR/aol40-cd/SETUP.EXE"
        echo '  $PYTHON client40/aol40_client.py configure ~/.wine-aol4/drive_c/America\ Online\ 4.0 --host '"$HOSTNAME"' --wine'
        echo '  wine "C:\\America Online 4.0\\waol.exe"'
    elif [ "$OS" = "macos" ]; then
        echo "  # macOS (Wine or CrossOver):"
        echo "  export WINEPREFIX=~/.wine-aol4"
        echo "  wine $INSTALL_DIR/aol40-cd/SETUP.EXE"
        echo '  $PYTHON client40/aol40_client.py configure ~/.wine-aol4/drive_c/America\ Online\ 4.0 --host '"$HOSTNAME"' --wine'
    else
        echo "  # Windows:"
        echo "  Run aol40-cd\\SETUP.EXE"
        echo '  python client40\\aol40_client.py configure "C:\\America Online 4.0" --host '"$HOSTNAME"
    fi
    echo
    echo "On the Sign On screen, choose Setup and set the location to TCP/IP."
    echo "Sign on with New User to create your first screen name."
    echo
}

# ---------- summary ----------

summary() {
    green "╔══════════════════════════════════════════════════════════╗"
    green "║                    Setup complete!                      ║"
    green "╚══════════════════════════════════════════════════════════╝"
    echo
    echo "  Server:     $HOSTNAME:$PORT"
    echo "  Install:    $INSTALL_DIR"
    echo "  Admin:      $INSTALL_DIR/run/admin '<expression>'"
    echo "  Mail setup: $INSTALL_DIR/run/mail-setup"
    echo "  Logs:       $INSTALL_DIR/run/server.log"
    echo
    echo "  Manage:"
    if [ "$OS" = "linux" ] && command -v systemctl >/dev/null 2>&1; then
        echo "    systemctl --user status aol-server"
        echo "    systemctl --user restart aol-server"
        echo "    journalctl --user -u aol-server -f"
    else
        echo "    $PYTHON $INSTALL_DIR/start.py"
    fi
    echo
    bold "  Next: install the AOL 4.0 client (see instructions above) and sign on!"
    echo
}

# ---------- main ----------

main() {
    banner
    detect_os
    install_deps
    clone_repo
    setup_domain
    install_services
    check_firewall
    setup_client
    summary
}

main "$@"
