# Modrinth CLI

A simple and lightweight command-line interface for interacting with the Modrinth API. Designed for quickly searching, filtering, and downloading mods and resourcepacks directly from your terminal.

## Installation

1. Ensure you have Python 3 installed.
2. Clone this repository: `git clone https://github.com/Dxrmy/modrinth-cli`
3. Navigate to the directory: `cd modrinth-cli`
4. Install the required dependencies: `pip install -r requirements.txt`

## Usage

Run the script using Python: `python3 modrinth.py [command] [arguments]`

### Commands

| Command | Description | Example |
|---|---|---|
| `search` | Search for projects with various filters (type, loader, version). | `python3 modrinth.py search "sodium" --type mod` |
| `download` | Download the latest version of a project by slug/id. | `python3 modrinth.py download sodium --version 1.20.1` |
| `filters` | List available filters (categories, loaders, versions). | `python3 modrinth.py filters categories` |

## Important Notice

- This tool interacts with the official Modrinth API but is not an official Modrinth product.
- Be respectful to the API limits when using automated scripts.
