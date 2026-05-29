# Clean Docker build cache and dangling images.
#
# WHY: Docker BuildKit (the default since v23) keeps every intermediate layer
# from every build. After ~10 iterations of changing Dockerfiles, the
# `docker_data.vhdx` file balloons to many GB. The images themselves are
# small (~600 MB); the bloat is almost entirely build cache.
#
# WHAT THIS DOES:
#   1. Prune ALL build cache (reclaimable space, usually GB).
#   2. Prune dangling images (untagged leftovers from rebuilds).
#   3. Print before/after disk usage.
#
# WHAT THIS DOES NOT TOUCH:
#   - Running containers and the images they use.
#   - Named volumes (e.g. pgdata holding your Postgres database).
#   - Tagged images currently referenced by docker-compose.
#
# PHYSICAL DISK RECLAMATION:
# Even after this script frees space INSIDE the vhdx file, Windows doesn't
# automatically shrink the file itself. To reclaim disk on the host:
#   1. Quit Docker Desktop from the tray
#   2. Run `wsl --shutdown` in an admin PowerShell
#   3. Run one of:
#        Optimize-VHD -Path "$env:LOCALAPPDATA\Docker\wsl\disk\docker_data.vhdx" -Mode Full
#        # OR via diskpart:
#        diskpart  -> select vdisk file="...docker_data.vhdx" -> compact vdisk -> exit
#   4. Restart Docker Desktop
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File docker/clean-cache.ps1

Write-Host "=== Docker disk usage BEFORE ===" -ForegroundColor Cyan
docker system df

Write-Host "`n=== Pruning build cache (this is usually the big win) ===" -ForegroundColor Cyan
docker builder prune -af

Write-Host "`n=== Pruning dangling images ===" -ForegroundColor Cyan
docker image prune -f

Write-Host "`n=== Docker disk usage AFTER ===" -ForegroundColor Cyan
docker system df

Write-Host "`nDone. To reclaim physical disk, see the comment block at the top of this script." -ForegroundColor Green
