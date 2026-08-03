$src = "f:\zhiwei_project\gift-picker-main\gift-picker-main"
$dst = "C:\Users\Jack\.agents\skills\gift-picker"

if (Test-Path $dst) {
    Remove-Item -Recurse -Force $dst
}

New-Item -ItemType Directory -Path "$dst\assets" -Force | Out-Null
New-Item -ItemType Directory -Path "$dst\references" -Force | Out-Null
New-Item -ItemType Directory -Path "$dst\scripts" -Force | Out-Null

$files = @(
    "SKILL.md",
    "CHANGELOG.md",
    "LICENSE",
    "README.md",
    ".gitignore",
    "assets\report-template.html",
    "references\data-sources.md",
    "references\flower-guide.md",
    "references\html-spec.md",
    "references\profile-schema.md",
    "references\relationship-stages.md",
    "references\scoring-model.md",
    "references\social-profiling.md",
    "references\budget-advisor.md",
    "references\seasonal-guide.md",
    "scripts\login_manager.py",
    "scripts\profile_manager.py"
)

foreach ($file in $files) {
    Copy-Item (Join-Path $src $file) (Join-Path $dst $file) -Force
    Write-Host "OK: $file"
}

Write-Host "DONE. Restart Codex and start new session."
