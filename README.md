# Modrinth CLI

A powerful, fast, and stateless command-line interface for interacting with the Modrinth API. Designed for both humans and AI agents.

## Features

- **Search**: Query the Modrinth API for mods, modpacks, resource packs, and shaders.
- **Download**: Instantly download specific versions or latest releases of any project.
- **Install (Bulk)**: Pass a text file of project slugs and bulk download all of them in one go!
- **Auto-Resolve**: Automatically download required dependencies for any mod.
- **Update**: Point to your `mods` folder, and it will hash your `.jar` files to check Modrinth for updates!
- **Scan**: Point to a directory, and it will identify the exact project, name, and version of every `.jar` or `.zip` file inside.
- **Uninstall**: Hash a directory and cleanly remove specific installed projects.
- **Unpack**: Natively extract `.mrpack` modpack archives directly into a destination folder.
- **Info & Versions**: View detailed project metadata and a complete version history.

## AI & Scripting Friendly Features
The Modrinth CLI was built from the ground up to be easily usable by other scripts, bash aliases, and AI agents.
- Add `--json` to any command (e.g. `search`, `info`, `versions`) to get clean, parseable JSON output instead of human-readable text.
- Standard Exit Codes: The script exits with status `0` on success, and `1` on failure (e.g., if a download fails, or 0 search results).
- **Fuzzy Fallback**: If you accidentally try to `download` using an invalid name (e.g., `xali's Bushy Leaves v3.5.0.zip`), the CLI will automatically clean the query, search Modrinth's API for the closest match, and safely auto-resolve the correct slug for you.
- **DuckDuckGo Fallback**: For completely obscure names, the CLI features a built-in DuckDuckGo HTML scraper to discover unindexed Modrinth URLs.

## Installation

No external dependencies are required. Just grab the script and run it with Python!

```bash
git clone https://github.com/Dxrmy/modrinth-cli.git
cd modrinth-cli
python modrinth.py -h
```

## Setup & Configuration

You can interactively set up a default Minecraft Version, Loader, and Destination folder so you don't have to specify them every time:

```bash
python modrinth.py init
```

Alternatively, you can pass them as environment variables:
`MODRINTH_VERSION`, `MODRINTH_LOADER`, `MODRINTH_DEST`.

## Usage Examples

**1. Searching for Mods**
```bash
python modrinth.py search "sodium" -v 1.20.1 -l fabric
```

**2. Downloading a Project**
```bash
# Downloads the latest version of sodium for 1.20.1 Fabric
python modrinth.py download sodium -v 1.20.1 -l fabric -d ./mods
```

**3. Bulk Installing from a Text File**
```bash
python modrinth.py install slugs.txt -v 1.20.1 -l fabric -d ./mods -R
```
*(The `-R` flag tells the CLI to automatically resolve and download required dependencies!)*

**4. Scanning Your Mods Folder**
```bash
python modrinth.py scan -d ~/.minecraft/mods
```

**5. Checking for Updates**
```bash
python modrinth.py update -d ~/.minecraft/mods
```

**6. Getting Machine-Readable JSON (For AI/Scripts)**
```bash
python modrinth.py --json search "iris"
```

## Tips
- Always use the precise **project slug** when downloading (e.g., `fabric-api`, not `Fabric API`).
- If you don't know the slug, run a `search` first or let the Fuzzy Fallback handle it!
