import argparse
import sys
import json
import urllib.request
import urllib.parse
from urllib.error import URLError, HTTPError
import hashlib
import os
import time

BASE_URL = "https://api.modrinth.com/v2"

def _request(endpoint, params=None):
    url = f"{BASE_URL}{endpoint}"
    if params:
        query_string = urllib.parse.urlencode(params, doseq=True)
        url = f"{url}?{query_string}"
    
    req = urllib.request.Request(url, headers={'User-Agent': 'modrinth-cli (github.com/Dxrmy/modrinth-cli)'})
    
    while True:
        try:
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode())
        except HTTPError as e:
            if e.code == 429:
                reset = int(e.headers.get('X-Ratelimit-Reset', 5))
                print(f"Rate limited (429). Sleeping for {reset} seconds to respect API limits...")
                time.sleep(reset + 1)
                continue
            if e.code == 404:
                print(f"Error 404: Not found -> {endpoint}")
                sys.exit(1)
            print(f"HTTP Error {e.code}: {e.read().decode()}")
            sys.exit(1)
        except URLError as e:
            print(f"URL Error: {e.reason}")
            sys.exit(1)

def check_file_hash(filepath, expected_hash):
    sha512 = hashlib.sha512()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            sha512.update(chunk)
    return sha512.hexdigest() == expected_hash

def download_file(url, dest_dir, filename, expected_hash=None):
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
        filepath = os.path.join(dest_dir, filename)
    else:
        filepath = filename

    if os.path.exists(filepath):
        if expected_hash and check_file_hash(filepath, expected_hash):
            print(f"File {filename} already exists and matches hash. Skipping download.")
            return filepath
        else:
            print(f"File {filename} already exists but hash differs. Overwriting...")

    print(f"Downloading {filename}...")
    try:
        urllib.request.urlretrieve(url, filepath)
    except Exception as e:
        print(f"Failed to download {filename}: {e}\n")
        return None
    
    if expected_hash:
        if not check_file_hash(filepath, expected_hash):
            print(f"ERROR: Hash mismatch for {filename}! The file might be corrupted.")
            os.remove(filepath)
            return None
        else:
            print(f"Hash verified successfully.")
            
    print(f"Successfully saved to {filepath}\n")
    return filepath

def get_primary_file(files):
    for f in files:
        if f.get('primary'):
            return f
    return files[0] if files else None

def project_info(slug):
    print(f"Fetching info for {slug}...")
    p = _request(f'/project/{slug}')
    print(f"\n[{p['project_type'].upper()}] {p['title']} ({p['slug']})")
    print(f"ID: {p['id']} | Status: {p['status']}")
    print(f"Downloads: {p['downloads']} | Followers: {p['followers']}")
    print(f"License: {p.get('license', {}).get('name', 'Unknown')}")
    print(f"Client: {p.get('client_side', 'unknown')} | Server: {p.get('server_side', 'unknown')}")
    if p.get('source_url'):
        print(f"Source: {p['source_url']}")
    if p.get('issues_url'):
        print(f"Issues: {p['issues_url']}")
    if p.get('wiki_url'):
        print(f"Wiki: {p['wiki_url']}")
    if p.get('discord_url'):
        print(f"Discord: {p['discord_url']}")
    print("-" * 60)
    print(p.get('description', 'No description provided.'))
    print("-" * 60)

def display_filters(filter_type):
    if filter_type == 'categories':
        data = _request('/tag/category')
        print("Available Categories:")
        for item in data:
            print(f" - {item['name']} ({item['project_type']})")
    elif filter_type == 'loaders':
        data = _request('/tag/loader')
        print("Available Loaders:")
        for item in data:
            print(f" - {item['name']}")
    elif filter_type == 'versions':
        data = _request('/tag/game_version')
        print("Available Game Versions:")
        for item in data:
            print(f" - {item['version']}")
    else:
        print("Unknown filter type. Choose from: categories, loaders, versions")

def search_projects(query, project_type, game_versions, loaders, categories, limit, offset):
    facets = []
    
    if project_type:
        facets.append([f'project_type:{project_type}'])
    if game_versions:
        facets.append([f'versions:{v}' for v in game_versions])
    if loaders:
        facets.append([f'categories:{l}' for l in loaders])
    if categories:
        facets.append([f'categories:{c}' for c in categories])
        
    params = {
        'query': query,
        'limit': limit,
        'offset': offset
    }
    if facets:
        params['facets'] = json.dumps(facets)
        
    data = _request('/search', params)
    
    print(f"Found {data['total_hits']} results. Showing {len(data['hits'])} results (Offset: {offset}):")
    print("-" * 60)
    for hit in data['hits']:
        categories = ", ".join(hit.get('display_categories', []))
        versions = hit.get('versions', [])
        if len(versions) > 6:
            versions_str = f"{versions[0]}, {versions[1]}, {versions[2]} ... {versions[-3]}, {versions[-2]}, {versions[-1]}"
        else:
            versions_str = ", ".join(versions)
            
        print(f"[{hit['project_type'].upper()}] {hit['title']} ({hit['slug']})")
        print(f"Description: {hit['description']}")
        print(f"Author: {hit['author']} | Downloads: {hit['downloads']}")
        print(f"Categories: {categories}")
        print(f"Versions: {versions_str}")
        print(f"Client: {hit.get('client_side', 'unknown')} | Server: {hit.get('server_side', 'unknown')}")
        print("-" * 60)

def download_project(slugs, dest_dir=None, version=None, loader=None):
    for slug in slugs:
        print(f"Fetching versions for {slug}...")
        params = {}
        if loader:
            params['loaders'] = json.dumps([loader])
        if version:
            params['game_versions'] = json.dumps([version])
            
        versions = _request(f'/project/{slug}/version', params)
        
        if not versions:
            print(f"No versions found matching the criteria for {slug}.")
            continue
            
        latest_version = versions[0]
        file = get_primary_file(latest_version.get('files', []))
        if not file:
            print(f"No files found in latest version for {slug}.")
            continue
            
        download_url = file['url']
        filename = file['filename']
        file_hash = file.get('hashes', {}).get('sha512')
        
        game_versions = latest_version.get('game_versions', [])
        v_loaders = latest_version.get('loaders', [])
        print(f"Selected version: {latest_version['name']} (Versions: {', '.join(game_versions)} | Loaders: {', '.join(v_loaders)})")
        
        if filename.endswith('.mrpack'):
            print(f"NOTICE: You downloaded a Modpack format (.mrpack). You cannot put this directly in your mods folder.")
            print(f"        Please import it using a compatible launcher like Prism Launcher or ATLauncher.")
            
        dependencies = latest_version.get('dependencies', [])
        required = [d['project_id'] for d in dependencies if d.get('dependency_type') == 'required']
        if required:
            print(f"WARNING: This version requires additional dependencies (Project IDs): {', '.join(required)}")
            
        download_file(download_url, dest_dir, filename, file_hash)

def list_versions(slug, version=None, loader=None):
    print(f"Fetching versions for {slug}...")
    params = {}
    if loader:
        params['loaders'] = json.dumps([loader])
    if version:
        params['game_versions'] = json.dumps([version])
        
    versions = _request(f'/project/{slug}/version', params)
    
    if not versions:
        print(f"No versions found matching the criteria for {slug}.")
        return
        
    print(f"{'VERSION ID':<20} | {'NAME':<40} | {'FILE'}")
    print("-" * 85)
    for v in versions:
        vid = v['id']
        name = v['name'][:37] + '...' if len(v['name']) > 40 else v['name']
        file = get_primary_file(v.get('files', []))
        filename = file['filename'] if file else "Unknown"
        print(f"{vid:<20} | {name:<40} | {filename}")

def download_version(version_id, dest_dir=None):
    print(f"Fetching version info for {version_id}...")
    v = _request(f'/version/{version_id}')
    file = get_primary_file(v.get('files', []))
    if not file:
        print("No files found in this version.")
        return
        
    download_url = file['url']
    filename = file['filename']
    file_hash = file.get('hashes', {}).get('sha512')
    
    if filename.endswith('.mrpack'):
        print(f"NOTICE: You downloaded a Modpack format (.mrpack). You cannot put this directly in your mods folder.")
        print(f"        Please import it using a compatible launcher like Prism Launcher or ATLauncher.")
        
    dependencies = v.get('dependencies', [])
    required = [d['project_id'] for d in dependencies if d.get('dependency_type') == 'required']
    if required:
        print(f"WARNING: This version requires additional dependencies (Project IDs): {', '.join(required)}")
        
    download_file(download_url, dest_dir, filename, file_hash)

def main():
    parser = argparse.ArgumentParser(
        description="Modrinth CLI - A feature-rich command-line interface for interacting with the Modrinth API.",
        epilog="Use 'modrinth.py <command> -h' for more information on a specific command."
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available Commands")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search for projects")
    search_parser.add_argument("query", nargs="?", default="", help="Search query")
    search_parser.add_argument("-t", "--type", choices=["mod", "modpack", "resourcepack", "shader"], help="Filter by project type")
    search_parser.add_argument("-v", "--version", action="append", help="Filter by game version (can be used multiple times)")
    search_parser.add_argument("-l", "--loader", action="append", help="Filter by loader (e.g., fabric, forge)")
    search_parser.add_argument("-c", "--category", action="append", help="Filter by category")
    search_parser.add_argument("-n", "--limit", type=int, default=10, help="Number of results to display (default: 10)")
    search_parser.add_argument("-o", "--offset", type=int, default=0, help="Offset for pagination (default: 0)")
    
    # Info command
    info_parser = subparsers.add_parser("info", help="Get detailed information about a specific project")
    info_parser.add_argument("slug", help="Project slug or ID")

    
    # Download command
    download_parser = subparsers.add_parser("download", help="Download projects")
    download_parser.add_argument("slugs", nargs="+", help="Project slugs or IDs (can specify multiple)")
    download_parser.add_argument("-v", "--version", help="Specific game version to download for")
    download_parser.add_argument("-l", "--loader", help="Specific loader to download for")
    download_parser.add_argument("-d", "--dest", help="Destination directory to save the file to")
    
    # Filters command
    filters_parser = subparsers.add_parser("filters", help="List available filters")
    filters_parser.add_argument("type", choices=["categories", "loaders", "versions"], help="Type of filters to list")
    
    # Versions command
    versions_parser = subparsers.add_parser("versions", help="List available versions/files for a project")
    versions_parser.add_argument("slug", help="Project slug or ID")
    versions_parser.add_argument("-v", "--version", help="Specific game version to filter")
    versions_parser.add_argument("-l", "--loader", help="Specific loader to filter")

    # Download-version command
    dl_ver_parser = subparsers.add_parser("download-version", help="Download a specific version by its ID")
    dl_ver_parser.add_argument("id", help="Version ID (from the 'versions' command)")
    dl_ver_parser.add_argument("-d", "--dest", help="Destination directory to save the file to")
    
    args = parser.parse_args()
    
    if args.command == "search":
        search_projects(args.query, args.type, args.version, args.loader, args.category, args.limit, args.offset)
    elif args.command == "info":
        project_info(args.slug)
    elif args.command == "download":
        download_project(args.slugs, args.dest, args.version, args.loader)
    elif args.command == "versions":
        list_versions(args.slug, args.version, args.loader)
    elif args.command == "download-version":
        download_version(args.id, args.dest)
    elif args.command == "filters":
        display_filters(args.type)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
