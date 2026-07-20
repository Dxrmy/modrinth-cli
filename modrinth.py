import argparse
import sys
import json
import urllib.request
import urllib.parse
from urllib.error import URLError, HTTPError
import hashlib
import os
import time
import zipfile
BASE_URL = "https://api.modrinth.com/v2"
CONFIG_FILE = os.path.expanduser("~/.modrinth-cli.json")
JSON_OUTPUT = False

# Hardcoded fallbacks for common acronyms or renamed projects that Modrinth search fails on
KNOWN_ALIASES = {
    'geo': 'glowing-emissive-ores',
    'fa': 'fresh-animations',
    'fa player': 'fa-player-extension',
    'fa expressions': 'just-expressions',
    'fa player expressions': 'just-expressions',
    'fa emissive': 'fresh-animations-emissive',
    'fa+player expressions': 'just-expressions',
    'weskerson': 'tools-and-utils',
    'weskersons 3d items': 'tools-and-utils'
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def init_config():
    print("--- Modrinth CLI Setup ---")
    mc_version = input("Default Minecraft Version (e.g. 1.20.1) [Leave blank to skip]: ").strip()
    loader = input("Default Loader (e.g. fabric, forge, neoforge) [Leave blank to skip]: ").strip()
    mc_dir = input("Default Base Directory (e.g. ~/.minecraft) [Leave blank to skip]: ").strip()
    
    config = {}
    if mc_version: config['version'] = mc_version
    if loader: config['loader'] = loader
    if mc_dir: config['dest'] = os.path.expanduser(mc_dir)
    
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
        
    print(f"\nConfiguration saved to {CONFIG_FILE}!")
    print("These defaults will now be used automatically if you don't specify them in commands.")

def _request(endpoint, params=None, is_post=False, post_data=None):
    endpoint = urllib.parse.quote(endpoint, safe='/:?=&')
    url = f"{BASE_URL}{endpoint}"
    if params:
        query_string = urllib.parse.urlencode(params, doseq=True)
        url = f"{url}?{query_string}"
    
    headers = {'User-Agent': 'modrinth-cli (github.com/Dxrmy/modrinth-cli)'}
    if is_post and post_data:
        headers['Content-Type'] = 'application/json'
        data_bytes = json.dumps(post_data).encode('utf-8')
        req = urllib.request.Request(url, data=data_bytes, headers=headers)
    else:
        req = urllib.request.Request(url, headers=headers)
    
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
                return None
            print(f"HTTP Error {e.code}: {e.read().decode()}")
            sys.exit(1)
        except URLError as e:
            print(f"URL Error: {e.reason}")
            sys.exit(1)

def suggest_mods(query):
    query_clean = query.replace('-', ' ').replace('_', ' ').replace("'", "")
    
    # Check known aliases first
    q_lower = query_clean.lower()
    for alias, slug in KNOWN_ALIASES.items():
        if alias in q_lower or q_lower.startswith(alias):
            print(f"\nDid you mean one of these?")
            print(f"  - {slug} (Known Alias for '{alias}')")
            return
            
    params = {'query': query_clean, 'limit': 3}
    url = f"{BASE_URL}/search?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={'User-Agent': 'modrinth-cli (github.com/Dxrmy/modrinth-cli)'})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if data and data.get('hits'):
                print(f"\nDid you mean one of these?")
                for hit in data['hits']:
                    print(f"  - {hit['slug']} ({hit['title']})")
    except Exception:
        pass

def get_suggestion(query):
    query_clean = query.replace('-', ' ').replace('_', ' ').replace("'", "")
    
    # Check known aliases first
    q_lower = query_clean.lower()
    for alias, slug in KNOWN_ALIASES.items():
        if alias in q_lower or q_lower.startswith(alias):
            return slug
            
    params = {'query': query_clean, 'limit': 1}
    url = f"{BASE_URL}/search?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={'User-Agent': 'modrinth-cli'})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if data and data.get('hits'):
                return data['hits'][0]['slug']
    except Exception:
        pass
    return None

def get_file_hash(filepath):
    sha512 = hashlib.sha512()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            sha512.update(chunk)
    return sha512.hexdigest()

def check_file_hash(filepath, expected_hash):
    return get_file_hash(filepath) == expected_hash

def get_routed_dest(base_dest, project_type):
    if not base_dest: return None
    basename = os.path.basename(base_dest.rstrip('/\\'))
    if basename in ['mods', 'shaderpacks', 'resourcepacks']:
        return base_dest
        
    if project_type == 'shader': return os.path.join(base_dest, 'shaderpacks')
    if project_type == 'resourcepack': return os.path.join(base_dest, 'resourcepacks')
    return os.path.join(base_dest, 'mods')

def download_file(url, dest_dir, filename, expected_hash=None, silent=False):
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)
        filepath = os.path.join(dest_dir, filename)
    else:
        filepath = filename

    if os.path.exists(filepath):
        if expected_hash and check_file_hash(filepath, expected_hash):
            if not silent: print(f"File {filename} already exists and matches hash. Skipping download.")
            return filepath
        else:
            if not silent: print(f"File {filename} already exists but hash differs. Overwriting...")

    if not silent: print(f"Downloading {filename}...")
    try:
        urllib.request.urlretrieve(url, filepath)
    except Exception as e:
        if not silent: print(f"Failed to download {filename}: {e}\n")
        return None
    
    if expected_hash:
        if not check_file_hash(filepath, expected_hash):
            print(f"ERROR: Hash mismatch for {filename}! The file might be corrupted.")
            os.remove(filepath)
            return None
            
    if not silent: print(f"Successfully saved to {filepath}\n")
    return filepath

def get_primary_file(files):
    for f in files:
        if f.get('primary'):
            return f
    return files[0] if files else None

def project_info(slug):
    if not JSON_OUTPUT: print(f"Fetching info for {slug}...")
    p = _request(f'/project/{slug}')
    if not p:
        if JSON_OUTPUT:
            print("{}")
            sys.exit(1)
        print(f"Error: Project '{slug}' not found.")
        suggest_mods(slug)
        sys.exit(1)
        
    if JSON_OUTPUT:
        print(json.dumps(p, indent=2))
        return
        
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
        if not data: return
        print("Available Categories:")
        for item in data:
            print(f" - {item['name']} ({item['project_type']})")
    elif filter_type == 'loaders':
        data = _request('/tag/loader')
        if not data: return
        print("Available Loaders:")
        for item in data:
            print(f" - {item['name']}")
    elif filter_type == 'versions':
        data = _request('/tag/game_version')
        if not data: return
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
    if not data: 
        if JSON_OUTPUT: print("[]")
        sys.exit(1)
        
    if JSON_OUTPUT:
        print(json.dumps(data, indent=2))
        return
    
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

def download_project(slugs, dest_dir=None, version=None, loader=None, auto_resolve=False, _resolved_set=None):
    if _resolved_set is None:
        _resolved_set = set()
    
    has_errors = False

    for slug in slugs:
        if slug in _resolved_set:
            continue
        _resolved_set.add(slug)
        
        print(f"Fetching versions for {slug}...")
        
        # Get project type for smart routing
        p_info = _request(f'/project/{slug}')
        if not p_info:
            print(f"Error: Project '{slug}' not found.")
            suggestion = get_suggestion(slug)
            if suggestion and suggestion != slug:
                print(f"Did you mean '{suggestion}'? Automatically falling back to '{suggestion}'...")
                slug = suggestion
                p_info = _request(f'/project/{slug}')
                if not p_info:
                    has_errors = True
                    continue
            else:
                suggest_mods(slug)
                has_errors = True
                continue
        p_type = p_info['project_type']
            
        params = {}
        if loader:
            params['loaders'] = json.dumps([loader])
        if version:
            params['game_versions'] = json.dumps([version])
            
        versions = _request(f'/project/{slug}/version', params)
        
        if not versions:
            print(f"No versions found matching the criteria for {slug}.")
            all_versions = _request(f'/project/{slug}/version')
            if all_versions:
                avail_gv = set()
                avail_ld = set()
                for v in all_versions:
                    avail_gv.update(v.get('game_versions', []))
                    avail_ld.update(v.get('loaders', []))
                sort_key = lambda s: [f"{int(x):05d}" if x.isdigit() else x for x in s.split('.')]
                print(f"Available Game Versions: {', '.join(sorted(avail_gv, key=sort_key))}")
                print(f"Available Loaders: {', '.join(sorted(avail_ld, key=sort_key))}")
            has_errors = True
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
            print(f"        Please import it using a compatible launcher like Prism Launcher, OR use 'modrinth.py unpack {filename}'")
            
        dependencies = latest_version.get('dependencies', [])
        required = [d['project_id'] for d in dependencies if d.get('dependency_type') == 'required']
        
        routed_dest = get_routed_dest(dest_dir, p_type)
        
        if required:
            if auto_resolve:
                print(f"Auto-resolving dependencies for {slug}...")
                download_project(required, dest_dir, version, loader, auto_resolve, _resolved_set)
            else:
                print(f"WARNING: This version requires additional dependencies (Project IDs): {', '.join(required)}")
                print(f"         (Tip: use --auto-resolve to download them automatically)")
            
        if not download_file(download_url, routed_dest, filename, file_hash):
            has_errors = True
    
    return not has_errors

def bulk_install(filepath, dest_dir, version, loader, auto_resolve):
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found.")
        return
    with open(filepath, 'r') as f:
        slugs = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    if not slugs:
        print("No valid slugs found in the file.")
        return
        
    print(f"Bulk installing {len(slugs)} projects...")
    download_project(slugs, dest_dir, version, loader, auto_resolve)

def list_versions(slug, version=None, loader=None):
    print(f"Fetching versions for {slug}...")
    params = {}
    if loader:
        params['loaders'] = json.dumps([loader])
    if version:
        params['game_versions'] = json.dumps([version])
        
    versions = _request(f'/project/{slug}/version', params)
    
    if versions is None:
        if JSON_OUTPUT:
            print("[]")
            sys.exit(1)
        print(f"Error: Project '{slug}' not found.")
        suggest_mods(slug)
        sys.exit(1)
        
    if JSON_OUTPUT:
        print(json.dumps(versions, indent=2))
        return
        
    if not versions:
        print(f"No versions found matching the criteria for {slug}.")
        all_versions = _request(f'/project/{slug}/version')
        if all_versions:
            avail_gv = set()
            avail_ld = set()
            for v in all_versions:
                avail_gv.update(v.get('game_versions', []))
                avail_ld.update(v.get('loaders', []))
            sort_key = lambda s: [f"{int(x):05d}" if x.isdigit() else x for x in s.split('.')]
            print(f"Available Game Versions: {', '.join(sorted(avail_gv, key=sort_key))}")
            print(f"Available Loaders: {', '.join(sorted(avail_ld, key=sort_key))}")
        if JSON_OUTPUT: print("[]")
        sys.exit(1)
        
    print(f"{'VERSION ID':<20} | {'NAME':<40} | {'FILE'}")
    print("-" * 85)
    for v in versions:
        vid = v['id']
        name = v['name'][:37] + '...' if len(v['name']) > 40 else v['name']
        file = get_primary_file(v.get('files', []))
        filename = file['filename'] if file else "Unknown"
        print(f"{vid:<20} | {name:<40} | {filename}")

def download_version(version_id, dest_dir=None, auto_resolve=False):
    print(f"Fetching version info for {version_id}...")
    v = _request(f'/version/{version_id}')
    if not v:
        print(f"Error: Version '{version_id}' not found.")
        return
        
    file = get_primary_file(v.get('files', []))
    if not file:
        print("No files found in this version.")
        return
        
    download_url = file['url']
    filename = file['filename']
    file_hash = file.get('hashes', {}).get('sha512')
    
    p_info = _request(f'/project/{v["project_id"]}')
    p_type = p_info['project_type'] if p_info else 'mod'
        
    routed_dest = get_routed_dest(dest_dir, p_type)
    
    if filename.endswith('.mrpack'):
        print(f"NOTICE: You downloaded a Modpack format (.mrpack). You cannot put this directly in your mods folder.")
        
    dependencies = v.get('dependencies', [])
    required = [d['project_id'] for d in dependencies if d.get('dependency_type') == 'required']
    if required:
        if auto_resolve:
            print(f"Auto-resolving dependencies...")
            game_versions = v.get('game_versions', [])
            loaders = v.get('loaders', [])
            gv = game_versions[0] if game_versions else None
            ld = loaders[0] if loaders else None
            download_project(required, dest_dir, gv, ld, auto_resolve=True)
        else:
            print(f"WARNING: This version requires additional dependencies (Project IDs): {', '.join(required)}")
        
    download_file(download_url, routed_dest, filename, file_hash)

def unpack_mrpack(filepath, dest_dir):
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found.")
        return
        
    if not dest_dir: 
        dest_dir = "."
    os.makedirs(dest_dir, exist_ok=True)
    
    try:
        with zipfile.ZipFile(filepath, 'r') as z:
            if 'modrinth.index.json' not in z.namelist():
                print(f"Error: {filepath} is not a valid .mrpack file (missing modrinth.index.json)")
                return
                
            with z.open('modrinth.index.json') as f:
                index = json.load(f)
                
            print(f"Unpacking Modpack: {index.get('name')} (Version {index.get('versionId')})")
            
            files = index.get('files', [])
            failed = []
            for file_info in files:
                downloads = file_info.get('downloads', [])
                if not downloads:
                    failed.append(file_info['path'])
                    continue
                    
                url = downloads[0]
                filename = os.path.basename(file_info['path'])
                file_dest = os.path.join(dest_dir, os.path.dirname(file_info['path']))
                expected_hash = file_info.get('hashes', {}).get('sha512')
                
                print(f"Downloading pack file: {filename}...")
                download_file(url, file_dest, filename, expected_hash, silent=True)
                
            print("Extracting overrides and configs...")
            for member in z.namelist():
                if member.startswith('overrides/') and not member.endswith('/'):
                    target = os.path.join(dest_dir, os.path.relpath(member, 'overrides'))
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with open(target, 'wb') as outfile:
                        outfile.write(z.read(member))
                        
            if failed:
                print("\nNOTICE: The following files could not be downloaded automatically (missing URLs, likely external like CurseForge):")
                for f in failed:
                    print(f" - {f}")
            print("\nModpack successfully unpacked!")
            
    except zipfile.BadZipFile:
        print(f"Error: {filepath} is not a valid zip archive.")

def update_mods(directory):
    if not os.path.isdir(directory):
        print(f"Error: Directory {directory} does not exist.")
        return
        
    print(f"Scanning {directory} for mods...")
    hashes = []
    file_map = {}
    for filename in os.listdir(directory):
        if filename.endswith('.jar'):
            filepath = os.path.join(directory, filename)
            sha512 = get_file_hash(filepath)
            hashes.append(sha512)
            file_map[sha512] = filepath
            
    if not hashes:
        print("No .jar files found.")
        return
        
    print(f"Found {len(hashes)} .jar files. Checking for updates via Modrinth API...")
    post_data = {"hashes": hashes, "algorithm": "sha512"}
    try:
        versions_data = _request('/version_files', is_post=True, post_data=post_data)
    except Exception as e:
        print(f"Error identifying files: {e}")
        return
        
    print("-" * 60)
    for h, v in versions_data.items():
        filepath = file_map[h]
        project_id = v['project_id']
        current_version_id = v['id']
        
        loaders = v.get('loaders', [])
        game_versions = v.get('game_versions', [])
        
        print(f"[{os.path.basename(filepath)}] (Identified as {v['name']})")
        
        params = {}
        if loaders: params['loaders'] = json.dumps([loaders[0]])
        if game_versions: params['game_versions'] = json.dumps([game_versions[0]])
        
        project_versions = _request(f'/project/{project_id}/version', params)
        if not project_versions: 
            continue
            
        latest = project_versions[0]
        if latest['id'] != current_version_id:
            print(f"  -> UPDATE AVAILABLE: {latest['name']}!")
        else:
            print(f"  -> Up to date.")

def uninstall_project(slug, directory):
    if not os.path.isdir(directory):
        print(f"Error: Directory {directory} does not exist.")
        return
        
    print(f"Fetching project info for '{slug}' to get ID...")
    p = _request(f'/project/{slug}')
    if not p:
        print(f"Error: Project '{slug}' not found on Modrinth.")
        suggest_mods(slug)
        return
    target_id = p['id']

    print(f"Scanning {directory} for installed mods...")
    hashes = []
    file_map = {}
    for filename in os.listdir(directory):
        if filename.endswith('.jar'):
            filepath = os.path.join(directory, filename)
            sha512 = get_file_hash(filepath)
            hashes.append(sha512)
            file_map[sha512] = filepath
            
    if not hashes:
        print("No .jar files found to uninstall.")
        return
        
    post_data = {"hashes": hashes, "algorithm": "sha512"}
    try:
        versions_data = _request('/version_files', is_post=True, post_data=post_data)
    except Exception as e:
        print(f"Error identifying files: {e}")
        return
        
    removed = False
    for h, v in versions_data.items():
        if v['project_id'] == target_id:
            filepath = file_map[h]
            print(f"Found match: {filepath} (Version: {v['name']})")
            os.remove(filepath)
            print("Successfully uninstalled.")
            removed = True
            
    if not removed:
        print(f"Could not find any installed files for project '{slug}' in {directory}.")

def main():
    parser = argparse.ArgumentParser(
        description="Modrinth CLI - A feature-rich command-line interface for interacting with the Modrinth API.",
        epilog="""
PROGRAMMATIC USAGE GUIDE & EXAMPLES:
  This CLI includes features specifically designed for programmatic use and scripting.
  
  General Scripting Tips:
   - Always append `--json` when you need to parse output (available for search, info, versions).
   - The script exits with status `1` on failure, `0` on success. Always check return codes.
   - For downloading, pass exactly the Modrinth project slug (e.g., 'fabric-api', 'iris').
   - If a download fails with a messy filename, the script will attempt a fuzzy auto-resolve.

  Examples:
   python modrinth.py search "sodium" --json
   python modrinth.py download fabric-api -v 1.20.1 -l fabric
   python modrinth.py versions iris -v 1.20.1 --json
   python modrinth.py info sodium --json
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available Commands")
    
    # Init command
    subparsers.add_parser("init", help="Interactively set up default configuration (version, loader, dest)")
    
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
    download_parser = subparsers.add_parser("download", help="Download projects (Scripting recommended)")
    download_parser.add_argument("slugs", nargs="+", help="Exact Project slugs or IDs to download (e.g., 'sodium', 'iris')")
    download_parser.add_argument("-v", "--version", help="Specific Minecraft version (e.g., '1.20.1', '26.2')")
    download_parser.add_argument("-l", "--loader", help="Specific loader (e.g., 'fabric', 'forge')")
    download_parser.add_argument("-d", "--dest", help="Destination folder (e.g., './mods')")
    download_parser.add_argument("-R", "--auto-resolve", action="store_true", help="Automatically resolve and download required dependencies")
    
    # Install command
    install_parser = subparsers.add_parser("install", help="Bulk install projects from a text file")
    install_parser.add_argument("filepath", help="Path to a text file containing project slugs/IDs")
    install_parser.add_argument("-v", "--version", help="Specific game version to download for")
    install_parser.add_argument("-l", "--loader", help="Specific loader to download for")
    install_parser.add_argument("-d", "--dest", help="Destination directory to save the file to")
    install_parser.add_argument("-R", "--auto-resolve", action="store_true", help="Automatically resolve and download required dependencies")

    # Uninstall command
    uninstall_parser = subparsers.add_parser("uninstall", help="Uninstall a specific mod by hashing jars and matching API")
    uninstall_parser.add_argument("slug", help="Project slug to uninstall")
    uninstall_parser.add_argument("-d", "--dir", default=".", help="Directory containing the installed .jar files")

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
    dl_ver_parser.add_argument("id", help="Version ID")
    dl_ver_parser.add_argument("-d", "--dest", help="Destination directory to save the file to")
    dl_ver_parser.add_argument("-R", "--auto-resolve", action="store_true", help="Automatically resolve and download required dependencies")
    
    # Unpack command
    unpack_parser = subparsers.add_parser("unpack", help="Unpack a .mrpack Modpack archive natively")
    unpack_parser.add_argument("filepath", help="Path to the .mrpack file")
    unpack_parser.add_argument("-d", "--dest", help="Destination directory to extract the modpack to")
    
    # Update command
    update_parser = subparsers.add_parser("update", help="Check a directory for mod updates")
    update_parser.add_argument("-d", "--dir", default=".", help="Directory containing .jar mods to check")

    global JSON_OUTPUT
    if '--json' in sys.argv:
        JSON_OUTPUT = True
        sys.argv.remove('--json')
    else:
        JSON_OUTPUT = False

    args = parser.parse_args()
    
    if args.command == "init":
        init_config()
        sys.exit(0)
    
    # Fallback to Config File & Environment Variables
    config = load_config()
    env_version = os.environ.get("MODRINTH_VERSION") or config.get("version")
    env_loader = os.environ.get("MODRINTH_LOADER") or config.get("loader")
    env_dest = os.environ.get("MODRINTH_DEST") or config.get("dest")
    
    if hasattr(args, 'version') and args.version is None and env_version:
        args.version = [env_version] if getattr(args, 'command', '') == 'search' else env_version
    if hasattr(args, 'loader') and args.loader is None and env_loader:
        args.loader = [env_loader] if getattr(args, 'command', '') == 'search' else env_loader
    if hasattr(args, 'dest') and args.dest is None and env_dest:
        args.dest = env_dest

    if args.command == "search":
        search_projects(args.query, args.type, args.version, args.loader, args.category, args.limit, args.offset)
    elif args.command == "info":
        project_info(args.slug)
    elif args.command == "download":
        if not download_project(args.slugs, args.dest, args.version, args.loader, args.auto_resolve):
            sys.exit(1)
    elif args.command == "install":
        bulk_install(args.filepath, args.dest, args.version, args.loader, args.auto_resolve)
    elif args.command == "uninstall":
        uninstall_project(args.slug, getattr(args, 'dir', '.'))
    elif args.command == "versions":
        list_versions(args.slug, args.version, args.loader)
    elif args.command == "download-version":
        download_version(args.id, args.dest, args.auto_resolve)
    elif args.command == "unpack":
        unpack_mrpack(args.filepath, getattr(args, 'dest', '.'))
    elif args.command == "update":
        update_mods(getattr(args, 'dir', '.'))
    elif args.command == "filters":
        display_filters(args.type)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
