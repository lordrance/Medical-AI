# Medical-AI 一键部署脚本
# 用法：.\deploy.ps1              → 部署默认分支（V4）
#       .\deploy.ps1 V5           → 部署 V5 分支
#       .\deploy.ps1 V4 --check   → 只检查状态，不部署
#
# 首次使用：
#   1. cp deploy\.deployrc.example deploy\.deployrc
#   2. 编辑 deploy\.deployrc，填上你的服务器 IP、用户名、SSH 密钥路径
#   3. .\deploy.ps1

param(
    [string]$Branch = "V4",
    [switch]$Check
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$ConfigFile = Join-Path $ScriptDir ".deployrc"

if (-not (Test-Path $ConfigFile)) {
    Write-Host "❌ 找不到 deploy\.deployrc" -ForegroundColor Red
    Write-Host ""
    Write-Host "首次使用请先配置：" -ForegroundColor Yellow
    Write-Host "  1. cp deploy\.deployrc.example deploy\.deployrc"
    Write-Host "  2. 编辑 deploy\.deployrc — 填上你的服务器 IP / 用户名 / SSH 密钥路径"
    Write-Host "  3. 重新运行 .\deploy.ps1"
    exit 1
}

# 读取配置
$config = @{}
Get-Content $ConfigFile | Where-Object { $_ -match '^\s*([A-Z_]+)\s*=\s*(.+)$' } | ForEach-Object {
    $config[$Matches[1]] = $Matches[2].Trim()
}

$ServerIP = $config["SERVER_IP"]
$ServerUser = $config["SERVER_USER"]
$SSHKey = $config["SSH_KEY"]
$RepoDir = $config["REPO_DIR"]

if (-not $ServerIP -or -not $ServerUser) {
    Write-Host "❌ .deployrc 缺少 SERVER_IP 或 SERVER_USER" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Medical-AI 部署" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  服务器: ${ServerUser}@${ServerIP}" -ForegroundColor Gray
Write-Host "  分支:   ${Branch}" -ForegroundColor Gray
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# 构建 SSH 命令
$SSHArgs = @("-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10")
if ($SSHKey) { $SSHArgs += @("-i", $SSHKey) }
$SSHTarget = "${ServerUser}@${ServerIP}"

if ($Check) {
    Write-Host "🔍 检查服务器状态..." -ForegroundColor Yellow
    $cmd = "cd ${RepoDir} && git log --oneline -3 && echo '---' && docker compose -f docker-compose.prod.yml ps"
    & ssh $SSHArgs $SSHTarget $cmd
    exit 0
}

# --- 第1步：推送本地代码 ---
Write-Host "📤 推送本地 ${Branch} 到 GitHub..." -ForegroundColor Yellow
Set-Location $ProjectRoot
git push origin $Branch

# --- 第2步：服务器拉取 + 重启 ---
Write-Host "🚀 服务器拉取并重启..." -ForegroundColor Yellow
$remoteCmd = "cd ${RepoDir} && bash deploy/deploy.sh ${Branch}"
& ssh $SSHArgs $SSHTarget $remoteCmd

Write-Host ""
Write-Host "=============================================" -ForegroundColor Green
Write-Host "  ✅ 部署完成" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
