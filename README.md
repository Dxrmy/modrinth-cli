# Modrinth CLI

A simple and lightweight command-line interface for interacting with the Modrinth API. Designed for quickly searching, filtering, and downloading mods and resourcepacks directly from your terminal.

## Installation / Execution

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

### Method 3: Standalone Executable
You can download the pre-compiled standalone executable from the [Releases page](https://github.com/Dxrmy/modrinth-cli/releases). This requires absolutely no python installation!
```bash
chmod +x modrinth-linux
./modrinth-linux search "sodium"
```

### Method 4: Clone & Run (For Developers)
1. Ensure you have Python 3 installed.
2. Clone this repository: `git clone https://github.com/Dxrmy/modrinth-cli`
3. Navigate to the directory: `cd modrinth-cli`
4. Install the required dependencies: `pip install -r requirements.txt`
5. Run the script using Python: `python3 modrinth.py [command] [arguments]`

## Usage

### Commands

| Command | Description | Example |
|---|---|---|
| `search` | Search for projects with various filters (type, loader, version). | `modrinth search "sodium" --type mod` |
| `download` | Download the latest version of a project by slug/id. | `modrinth download sodium --version 1.20.1` |
| `filters` | List available filters (categories, loaders, versions). | `modrinth filters categories` |

*(Note: The examples above assume you are using the alias or executable. Adjust the prefix if you are using the one-liner or running it via python3 directly.)*

## Important Notice

- This tool interacts with the official Modrinth API but is not an official Modrinth product.
- Be respectful to the API limits when using automated scripts.
