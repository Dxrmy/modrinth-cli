# Modrinth CLI

A command-line interface for managing Minecraft mods, resource packs, shaders, and modpacks.

## Features

- **Search & Discovery**: Query Modrinth for mods, modpacks, resource packs, and shaders with advanced filtering (game version, loader, categories, facets, and sorting).
- **Direct & Bulk Download**: Download projects by slug, ID, or version ID with automatic dependency resolution (`-R`).
- **Declarative Modpack Management (`pack.toml`)**:
  - `pack init`: Initialize a declarative modpack manifest.
  - `pack add / remove`: Manage declared mods from **Modrinth**, **CurseForge**, and **GitHub Releases**.
  - `pack sync`: Synchronize your local mods folder with `pack.toml` in one command.
  - `pack export`: Compile declared mods and `overrides/` folder into a standard `.mrpack` archive.
- **Native `.mrpack` Unpacker**: Extract and download all indexed files from `.mrpack` archives directly to any directory.
- **In-Place File Upgrades**:
  - `upgrade <file.jar>`: Directly upgrade an individual `.jar` file in-place to its latest compatible version.
  - `upgrade-all`: Scan an entire folder, detect outdated mods, and batch upgrade them with interactive confirmation.
- **Global Disk Download Cache**: Content-addressed local disk cache with SHA512 hash validation to avoid redundant downloads across game instances.
- **Deep Inspection & Changelogs**:
  - `changelog`: View formatted markdown release notes directly in your terminal.
  - `inspect`: Technical inspection of projects, versions, and user profiles.
  - `--get-property`: Extract single metadata fields for shell pipelines.
- **Smart Fallback & Fuzzy Resolver**: Built-in query cleaner, DuckDuckGo scraper fallback, and Surfraw integration for unindexed queries or messy filenames.

## Automation & Scripting Features

Notes for scripting:
- `--json` prints machine-readable JSON on `stdout`.
- Exit code is `0` on success and `1` on failure.
- Uses only standard Python libraries (`urllib`, `hashlib`, `json`, `zipfile`).

## Installation

```bash
git clone https://github.com/Dxrmy/modrinth-cli.git
cd modrinth-cli
python modrinth.py -h
```

## Setup & Configuration

Configure default Minecraft versions, loaders, directories, and cache settings:

```bash
python modrinth.py init
```

Alternatively, configure defaults via environment variables:
`MODRINTH_VERSION`, `MODRINTH_LOADER`, `MODRINTH_DEST`.

## Usage Examples

### 1. Searching & Inspecting Projects
```bash
# Search for mods
python modrinth.py search "sodium" -v 1.20.1 -l fabric

# View detailed metadata or a single property
python modrinth.py info sodium
python modrinth.py info sodium -p client_side

# View recent release changelogs
python modrinth.py changelog sodium -c 3

# Inspect a user profile or version
python modrinth.py inspect user Dxrmy --json
python modrinth.py inspect project AANobbMI --json
```

### 2. Downloading & Dependency Auto-Resolution
```bash
# Download a mod and automatically install its required dependencies
python modrinth.py download iris -v 1.20.1 -l fabric -d ./mods -R

# Bulk install from a text file list of slugs
python modrinth.py install mods.txt -v 1.20.1 -l fabric -d ./mods -R
```

### 3. In-Place File Upgrading
```bash
# Upgrade a specific jar file in-place
python modrinth.py upgrade ./mods/sodium-fabric.jar -v 1.20.1 -l fabric

# Scan and upgrade all mods in a directory
python modrinth.py upgrade-all -d ~/.minecraft/mods -v 1.20.1 -l fabric -y
```

### 4. Declarative Modpack Management (`pack.toml`)
```bash
# 1. Initialize a new pack
python modrinth.py pack init "My Survival Pack" -v 1.20.1 -l fabric

# 2. Add mods from Modrinth, GitHub Releases, or CurseForge
python modrinth.py pack add sodium
python modrinth.py pack add iris
python modrinth.py pack add FabricMC/fabric-loader --source github

# 3. Synchronize mods with your local directory
python modrinth.py pack sync -d ./mods -R

# 4. Export to a distributable .mrpack archive
python modrinth.py pack export -f mrpack -o MyPack.mrpack
```

### 5. Modpack Unpacking (`.mrpack`)
```bash
python modrinth.py unpack MyPack.mrpack -d ~/.minecraft
```

### 6. Local Download Cache Management
```bash
# Check cache size and status
python modrinth.py cache status

# Clear local download cache
python modrinth.py cache clear
```

## Tips
- Use `-R / --auto-resolve` whenever downloading mods to ensure all upstream dependencies are satisfied.
- Use `pack.toml` in your modpack repositories to version control your mods in Git without committing `.jar` binaries.

## License

MIT License. See [LICENSE](LICENSE) for details.
