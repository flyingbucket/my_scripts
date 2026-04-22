#!/bin/bash

# Initialize git
git init

# Create .gitignore
cat <<EOF >.gitignore
build/*
!build/*.pdf
*.aux
*.log
*.fdb_latexmk
*.fls
*.synctex.gz
EOF

# Create .latexmkrc
cat <<EOF >.latexmkrc
\$out_dir = 'build';

if (! -d \$out_dir) {
    mkdir \$out_dir;
}
EOF

echo "Standard .gitignore file and .latexmkrc file created."
echo "Initialization finished."
