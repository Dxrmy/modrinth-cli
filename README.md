# Modrinth CLI

A blazing fast, insanely feature-rich command-line interface for the Modrinth API. Designed for quickly searching, managing, updating, and downloading mods, resource packs, and shaders directly from your terminal.

## Execution Methods

You have multiple ways to use this tool depending on your preference.

### Method 1: The Quick One-Liner (No Download)
Run the script directly from GitHub without saving any files locally or explicitly typing `python3`:
```bash
curl -sL https://raw.githubusercontent.com/Dxrmy/modrinth-cli/main/run.sh | bash -s -- search "sodium"
```

### Method 2: Temporary Alias (Cleanest)
Set up a temporary alias in your terminal to use the command smoothly during your current session:
```bash
alias modrinth="curl -sL https://raw.githubusercontent.com/Dxrmy/modrinth-cli/main/modrinth.py | python3 -"
modrinth search "sodium"
```

### Method 3: Standalone Executable (No Python Required)
You can download the pre-compiled standalone executable from the [Releases page](https://github.com/Dxrmy/modrinth-cli/releases).
```bash
chmod +x modrinth-linux
./modrinth-linux search "sodium"
```

---

## Configuration (`modrinth init`)

Tired of typing `-v 1.20.1 -l fabric` every time? Run the interactive setup!
```bash
modrinth init
```
This will ask you for your default Minecraft version, loader, and base directory (e.g. `~/.minecraft`), saving it to `~/.modrinth-cli.json`. The CLI will automatically use these defaults globally!

*(Alternatively, you can export `MODRINTH_VERSION`, `MODRINTH_LOADER`, and `MODRINTH_DEST` environment variables).*

---

## Core Commands

### 🔍 Search & Discovery
Search for mods, filter by loaders/versions, and view rich formatting including Client/Server support.
```bash
modrinth search "sodium" -v 1.20.1 -l fabric --limit 20
```

### 📥 Downloading Mods
Download mods instantly, with built-in hash verification to prevent corrupted jars.
```bash
modrinth download sodium lithium phosphor -v 1.20.1 -l fabric
```

**Auto-Resolve Dependencies (`-R`)**
Don't want to crash because you forgot the Fabric API? Use `-R` to automatically resolve and recursively download all required libraries!
```bash
modrinth download sodium -R
```

**Smart Routing**
If you configured a base directory (or pass `-d ~/.minecraft`), the CLI will automatically route mods to `/mods`, resource packs to `/resourcepacks`, and shaders to `/shaderpacks`!

### ℹ️ Project Info & File Versions
Get detailed data (Source Code URLs, issue trackers, discord links, follower counts).
```bash
modrinth info fallingleaves
```

See exactly what files are available to download, to pick the precise variant you need (e.g., "With Eyes" vs "Eyeless").
```bash
modrinth versions tras-fresh-player
modrinth download-version BX6pU42f
```

---

## Advanced Commands

### 🔄 Bulk Install
Given a text file (`modlist.txt`) full of mod slugs, download them all at once!
```bash
modrinth install modlist.txt -R
```

### 📦 Unpack Modpacks Natively
Tired of third-party launchers? Natively unpack `.mrpack` archives directly from the CLI. It will automatically read the index, download every single jar file, and extract all config overrides!
```bash
modrinth unpack optimize.mrpack -d ~/.minecraft
```

### 🚀 Update Checker
Scan your entire `mods/` directory. The CLI will calculate the SHA-512 hashes of all local jars, send a bulk API request to identify them, and notify you if newer updates exist!
```bash
modrinth update -d ~/.minecraft/mods
```

### 🗑️ Uninstall Mods
Cleanly remove a mod from your mods folder by hashing the files and finding the exact one you want to delete.
```bash
modrinth uninstall sodium -d ~/.minecraft/mods
```

---

## Important Notice

- This tool interacts with the official Modrinth API but is not an official Modrinth product.
- Be respectful to the API limits when using automated scripts (the CLI has built-in Rate Limit handlers to automatically sleep and protect you from 429s).
