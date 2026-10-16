# aolserver installer for Windows — run with:
#   powershell -ExecutionPolicy Bypass -File install.ps1
# or from the repo: right-click install.ps1 -> "Run with PowerShell"
param(
    [string]$InstallDir = "$env:USERPROFILE\aolserver",
    [int]$Port = 5190
)
$ErrorActionPreference = "Stop"

function Bold($s)   { Write-Host $s -ForegroundColor White }
function Green($s)  { Write-Host $s -ForegroundColor Green }
function Yellow($s) { Write-Host $s -ForegroundColor Yellow }
function Red($s)    { Write-Host $s -ForegroundColor Red }
function Ask($prompt) { $r = Read-Host $prompt; return $r }

Write-Host ""
Bold "+==========================================================+"
Bold "|              aolserver - AOL 3.0/4.0 host                |"
Bold "|        Original client, rebuilt server, 2026 content      |"
Bold "+==========================================================+"
Write-Host ""

# --- check Python ---
$py = $null
foreach ($name in @("python3", "python", "py")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) {
        $ver = & $cmd.Source -c "import sys; print(sys.version_info >= (3, 10))" 2>$null
        if ($ver -eq "True") { $py = $cmd.Source; break }
    }
}
if (-not $py) {
    Red "Python 3.10+ is required. Install it from https://www.python.org/downloads/ and re-run."
    exit 1
}
Green "  Python: $((& $py --version 2>&1))"

# --- check git ---
$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
    Red "git is required. Install it from https://git-scm.com/download/win and re-run."
    exit 1
}
Green "  git: $((git --version 2>&1))"

# --- check Chrome/Edge ---
$browser = $null
foreach ($p in @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
)) {
    if (Test-Path $p) { $browser = $p; break }
}
if ($browser) {
    Green "  Browser: $browser (World Wide Web will show real pages)"
} else {
    Yellow "  Chrome/Edge: not found (Web browsing inside AOL will be text-only)"
    Write-Host "  Install Chrome or Edge for full web page rendering inside AOL."
}
Write-Host ""

# --- clone / update ---
if (Test-Path (Join-Path $InstallDir ".git")) {
    Bold "Updating existing installation in $InstallDir..."
    git -C $InstallDir pull --ff-only 2>$null
    if ($LASTEXITCODE -ne 0) { git -C $InstallDir pull --rebase }
} else {
    Bold "Downloading aolserver to $InstallDir..."
    git clone "https://github.com/kachowtowmater/aolserver.git" $InstallDir
}
Green "  Done."
Write-Host ""

# --- hostname ---
Bold "=== Server configuration ==="
Write-Host ""
Write-Host "Your server needs a hostname that AOL clients will connect to."
Write-Host "This can be a domain name (aol.example.com), a LAN hostname, or localhost."
Write-Host ""
$hostname = Ask "Server hostname [localhost]"
if (-not $hostname) { $hostname = "localhost" }
Write-Host ""

# --- mail ---
Bold "=== Internet mail ==="
Write-Host ""
Write-Host "Mail between members always works.  To let members send and receive"
Write-Host "real Internet email (screenname@yourdomain.com), set it up now."
Write-Host ""
Write-Host "  1) Skip for now (member-to-member mail only)"
Write-Host "  2) Use a Gmail/Fastmail/iCloud account (easiest)"
Write-Host "  3) Host your own domain (screenname@yourdomain.com)"
Write-Host ""
$mailChoice = Ask "Choice [1]"
if (-not $mailChoice) { $mailChoice = "1" }

switch ($mailChoice) {
    "2" {
        Write-Host ""
        Bold "Running mail setup wizard..."
        & $py (Join-Path $InstallDir "server" | Join-Path -ChildPath "mailsetup.py")
    }
    "3" {
        Write-Host ""
        $domain = Ask "Your domain (e.g. my90s.net)"
        if ($domain) {
            Bold "Setting up domain mail for $domain..."
            $listenPort = Ask "SMTP listen port [2525]"
            if (-not $listenPort) { $listenPort = "2525" }
            Write-Host ""
            Write-Host "For sending mail OUT, you need an SMTP relay (recommended) or direct delivery."
            Write-Host "  1) SMTP relay (e.g. Gmail, Fastmail, SMTP2GO, Mailgun, Amazon SES)"
            Write-Host "  2) Direct delivery (needs static IP, reverse DNS, outbound port 25)"
            Write-Host ""
            $outMethod = Ask "Outbound method [1]"
            if (-not $outMethod) { $outMethod = "1" }
            if ($outMethod -eq "1") {
                $smtpHost = Ask "SMTP relay host (e.g. smtp.gmail.com)"
                $smtpPort = Ask "SMTP relay port [587]"
                if (-not $smtpPort) { $smtpPort = "587" }
                $smtpUser = Ask "SMTP username"
                $smtpPass = Read-Host "SMTP password" -AsSecureString
                $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($smtpPass)
                $plainPass = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
                $mailsetup = Join-Path $InstallDir "server" | Join-Path -ChildPath "mailsetup.py"
                $plainPass | & $py $mailsetup `
                    --mode domain --domain $domain --listen-port $listenPort `
                    --outbound relay --smtp-host $smtpHost --smtp-port $smtpPort `
                    --smtp-user $smtpUser --password-stdin
            } else {
                $mailsetup = Join-Path $InstallDir "server" | Join-Path -ChildPath "mailsetup.py"
                & $py $mailsetup `
                    --mode domain --domain $domain --listen-port $listenPort `
                    --outbound direct
            }
            Write-Host ""
            Bold "DNS records to create:"
            $mailsetup = Join-Path $InstallDir "server" | Join-Path -ChildPath "mailsetup.py"
            & $py $mailsetup --dns
        } else {
            Yellow "No domain entered, skipping mail setup."
        }
    }
    default {
        Write-Host "  Skipped.  Run '$InstallDir\run\mail-setup' any time to set it up."
    }
}
Write-Host ""

# --- service ---
Bold "=== Start on boot ==="
Write-Host ""
Write-Host "Install a Task Scheduler job so aolserver starts automatically?"
$installSvc = Ask "[Y/n]"
if (-not $installSvc) { $installSvc = "y" }
if ($installSvc -match "^[Yy]") {
    $startPy = Join-Path $InstallDir "start.py"
    $action = New-ScheduledTaskAction -Execute $py -Argument "`"$startPy`"" -WorkingDirectory $InstallDir
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit 0
    Register-ScheduledTask -TaskName "aolserver" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName "aolserver"
    Green "  Task installed and started."
    Write-Host "  Stop:    Stop-ScheduledTask -TaskName aolserver"
    Write-Host "  Remove:  Unregister-ScheduledTask -TaskName aolserver"
}
Write-Host ""

# --- firewall ---
Bold "=== Firewall ==="
Write-Host ""
Write-Host "AOL clients connect to TCP port $Port."
Write-Host "If clients connect from other machines, open it:"
Write-Host "  netsh advfirewall firewall add rule name=aolserver dir=in action=allow protocol=TCP localport=$Port"
Write-Host "If clients connect from outside your LAN, also forward port $Port on your router."
Write-Host ""

# --- client ---
Bold "=== AOL 4.0 client ==="
Write-Host ""
Write-Host "The server is ready. Now you need the original AOL 4.0 client to connect to it."
Write-Host ""
Write-Host "Download the client CD from archive.org:"
Write-Host "  cd $InstallDir"
Write-Host "  $py client40\aol40_client.py fetch"
Write-Host ""
Write-Host "Then install and configure it:"
Write-Host "  Run aol40-cd\SETUP.EXE (if it refuses: Properties > Compatibility > Windows 98/ME)"
Write-Host "  $py client40\aol40_client.py configure `"C:\America Online 4.0`" --host $hostname"
Write-Host ""
Write-Host "On the Sign On screen, choose Setup and set the location to TCP/IP."
Write-Host "Sign on with New User to create your first screen name."
Write-Host ""

# --- done ---
Green "+==========================================================+"
Green "|                    Setup complete!                        |"
Green "+==========================================================+"
Write-Host ""
Write-Host "  Server:     ${hostname}:$Port"
Write-Host "  Install:    $InstallDir"
Write-Host "  Admin:      $py $InstallDir\run\admin '<expression>'"
Write-Host "  Mail setup: $py $InstallDir\server\mailsetup.py"
Write-Host ""
Bold "  Next: install the AOL 4.0 client (see instructions above) and sign on!"
Write-Host ""
