# Initialize Git Repository
git init

# Create main branch
git checkout -b main

# Add all files
git add .

# Commit
git commit -m "Initial commit v1.0.0"

# Tag version
git tag v1.0.0

Write-Host "=================================================="
Write-Host "Local repository initialized with branch 'main' and tag 'v1.0.0'."
Write-Host "To push to GitHub, please follow these steps:"
Write-Host "1. Create a NEW repository on GitHub (empty, without README)."
Write-Host "2. Copy the repository URL."
Write-Host "3. Run the following commands in your terminal:"
Write-Host "   git remote add origin <your-github-repo-url>"
Write-Host "   git push -u origin main --tags"
Write-Host "=================================================="
